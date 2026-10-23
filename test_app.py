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

    def post_entry(self, name: str, message: str) -> tuple[int, dict[str, str], str]:
        body = urlencode({"name": name, "message": message})
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
        self.assertEqual(headers["Location"], "/?added=1")
        status, _, body = self.request("GET", "/?added=1")

        self.assertEqual(status, 200)
        self.assertIn("&lt;b&gt;방문자&lt;/b&gt;", body)
        self.assertIn("&lt;script&gt;alert(&quot;안녕&quot;)&lt;/script&gt;", body)
        self.assertNotIn("<script>alert", body)
        self.assertIn("방명록을 저장했습니다.", body)

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
