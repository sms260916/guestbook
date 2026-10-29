import http.client
import os
from uuid import uuid4
from unittest.mock import patch
from pathlib import Path
import threading
import unittest
from urllib.parse import urlencode

from app import create_server, connect_database, DatabaseSettings


@unittest.skipUnless(os.environ.get("GUESTBOOK_TEST_POSTGRES") == "1", "별도 PostgreSQL 테스트 DB 필요")
class GuestbookAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = DatabaseSettings.from_env()
        self.schema = "guestbook_test_" + uuid4().hex
        self.real_connect = connect_database
        with self.real_connect(self.settings) as connection:
            connection.execute(f'CREATE SCHEMA "{self.schema}"')
        def isolated_connect(settings):
            connection = self.real_connect(settings)
            connection.execute(f'SET search_path TO "{self.schema}"')
            return connection
        self.connect_patch = patch("app.connect_database", side_effect=isolated_connect)
        self.connect_patch.start()
        self.addCleanup(self.clean_database)
        self.server = create_server(self.settings, "127.0.0.1", 0)
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.server_thread.start()
        self.host, self.port = self.server.server_address

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join()

    def clean_database(self):
        self.connect_patch.stop()
        with self.real_connect(self.settings) as connection:
            connection.execute(f'DROP SCHEMA "{self.schema}" CASCADE')

    def server_connection(self):
        import app
        return app.connect_database(self.settings)

    def request(
        self,
        method: str,
        path: str,
        body: str | None = None,
    ) -> tuple[int, dict[str, str], str]:
        connection = http.client.HTTPConnection(self.host, self.port)
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        result = (
            response.status,
            dict(response.getheaders()),
            response.read().decode("utf-8"),
        )
        connection.close()
        return result

    def post_entry(
        self,
        name: str,
        message: str,
        parent_id: int | None = None,
    ) -> tuple[int, dict[str, str], str]:
        values = {"name": name, "message": message}
        if parent_id is not None:
            values["parent_id"] = str(parent_id)
        body = urlencode(values)
        return self.request("POST", "/", body)

    def test_home_shows_form_and_empty_state(self) -> None:
        status, _, body = self.request("GET", "/")

        self.assertEqual(status, 200)
        self.assertIn('method="post"', body)
        self.assertIn("아직 등록된 글이 없습니다.", body)

    def test_post_persists_and_escapes_user_content(self) -> None:
        status, headers, _ = self.post_entry(
            "<b>방문자</b>",
            '<script>alert("안녕")</script>',
        )

        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/?saved=1")
        status, _, body = self.request("GET", "/?saved=1")

        self.assertEqual(status, 200)
        self.assertIn("&lt;b&gt;방문자&lt;/b&gt;", body)
        self.assertIn("&lt;script&gt;alert(&quot;안녕&quot;)&lt;/script&gt;", body)
        self.assertNotIn("<script>alert", body)
        self.assertIn("새 글을 남겼습니다.", body)

    def test_reply_is_saved_under_root_and_nested_reply_is_rejected(self) -> None:
        status, _, _ = self.post_entry("원글 작성자", "원글 내용")
        self.assertEqual(status, 303)
        with self.server_connection() as connection:
            root_id = connection.execute(
                "SELECT id FROM guestbook_entries WHERE parent_id IS NULL"
            ).fetchone()[0]

        status, headers, _ = self.post_entry("댓글 작성자", "첫 댓글", root_id)
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "/?saved=reply")
        status, _, body = self.request("GET", "/?saved=reply")
        self.assertEqual(status, 200)
        self.assertIn("원글 내용", body)
        self.assertIn("첫 댓글", body)
        self.assertIn("댓글을 남겼습니다.", body)

        with self.server_connection() as connection:
            reply_id = connection.execute(
                "SELECT id FROM guestbook_entries WHERE parent_id = %s",
                (root_id,),
            ).fetchone()[0]
        status, _, body = self.post_entry("다른 사람", "대댓글", reply_id)
        self.assertEqual(status, 400)
        self.assertIn("답글은 원글에만 작성할 수 있습니다.", body)
        with self.server_connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM guestbook_entries"
            ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_initialization_preserves_existing_entries(self):
        from app import initialize_database, add_entry, get_recent_entries
        add_entry(self.settings, "이전 작성자", "이전 글")
        initialize_database(self.settings)
        self.assertEqual(get_recent_entries(self.settings)[0].message, "이전 글")

    def test_failed_transaction_rolls_back(self):
        import psycopg
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            with self.server_connection() as connection:
                connection.execute("INSERT INTO guestbook_entries (name, message) VALUES (%s, %s)", ("롤백", "첫 글"))
                connection.execute("INSERT INTO guestbook_entries (name, message, parent_id) VALUES (%s, %s, %s)", ("실패", "댓글", 999999))
        with self.server_connection() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM guestbook_entries").fetchone()[0], 0)

    def test_invalid_entry_is_rejected_without_saving(self) -> None:
        status, _, body = self.post_entry(" ", "내용")

        self.assertEqual(status, 400)
        self.assertIn("이름은 1~40자로 입력해 주세요.", body)
        with self.server_connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM guestbook_entries"
            ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_only_newest_fifty_entries_are_shown(self) -> None:
        for number in range(51):
            status, _, _ = self.post_entry(f"이름{number}", f"글{number}")
            self.assertEqual(status, 303)

        status, _, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("글50", body)
        self.assertNotIn("글0</p>", body)
        self.assertIn("prefers-reduced-motion", body)
        self.assertIn('class="leaves"', body)

        with self.server_connection() as connection:
            tables = connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
            ).fetchall()
            count = connection.execute(
                "SELECT COUNT(*) FROM guestbook_entries"
            ).fetchone()[0]
        self.assertEqual(tables, [("guestbook_entries",)])
        self.assertEqual(count, 51)


if __name__ == "__main__":
    unittest.main()
