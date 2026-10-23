import http.client
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.parse import urlencode

from app import create_server


class GuestbookAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "guestbook.sqlite3"
        self.server = create_server(self.db_path, "127.0.0.1", 0)
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
        self.temp_dir.cleanup()

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
        with closing(sqlite3.connect(self.db_path)) as connection:
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

        with closing(sqlite3.connect(self.db_path)) as connection:
            reply_id = connection.execute(
                "SELECT id FROM guestbook_entries WHERE parent_id = ?",
                (root_id,),
            ).fetchone()[0]
        status, _, body = self.post_entry("다른 사람", "대댓글", reply_id)
        self.assertEqual(status, 400)
        self.assertIn("답글은 원글에만 작성할 수 있습니다.", body)
        with closing(sqlite3.connect(self.db_path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM guestbook_entries"
            ).fetchone()[0]
        self.assertEqual(count, 2)

    def test_previous_database_is_migrated_without_losing_entries(self) -> None:
        old_db_path = Path(self.temp_dir.name) / "previous.sqlite3"
        with closing(sqlite3.connect(old_db_path)) as connection:
            connection.execute(
                """
                CREATE TABLE guestbook_entries (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "INSERT INTO guestbook_entries (name, message) VALUES (?, ?)",
                ("이전 작성자", "이전 글"),
            )
            connection.commit()

        migrated_server = create_server(old_db_path, "127.0.0.1", 0)
        migrated_server.server_close()
        with closing(sqlite3.connect(old_db_path)) as connection:
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(guestbook_entries)"
                )
            }
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            existing_entry = connection.execute(
                "SELECT name, message, parent_id FROM guestbook_entries"
            ).fetchone()
        self.assertIn("parent_id", columns)
        self.assertEqual(tables, [("guestbook_entries",)])
        self.assertEqual(existing_entry, ("이전 작성자", "이전 글", None))

    def test_invalid_entry_is_rejected_without_saving(self) -> None:
        status, _, body = self.post_entry(" ", "내용")

        self.assertEqual(status, 400)
        self.assertIn("이름은 1~40자로 입력해 주세요.", body)
        with closing(sqlite3.connect(self.db_path)) as connection:
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

        with closing(sqlite3.connect(self.db_path)) as connection:
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            count = connection.execute(
                "SELECT COUNT(*) FROM guestbook_entries"
            ).fetchone()[0]
        self.assertEqual(tables, [("guestbook_entries",)])
        self.assertEqual(count, 51)


if __name__ == "__main__":
    unittest.main()
