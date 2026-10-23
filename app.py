"""표준 라이브러리만 사용하는 간단한 방명록 웹 서버."""

from contextlib import closing
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

BASE_DIR = Path(__file__).resolve().parent
HTML_PATH = BASE_DIR / "index.html"
MAX_NAME_LENGTH = 40
MAX_MESSAGE_LENGTH = 1000
MAX_FORM_BYTES = 8192
VISIBLE_ENTRY_LIMIT = 50


def initialize_database(db_path: Path) -> None:
    """방명록 글을 저장하는 단일 테이블을 준비한다."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path, timeout=5)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS guestbook_entries (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()


def add_entry(db_path: Path, name: str, message: str) -> None:
    """검증된 글을 SQL 매개변수로 저장한다."""
    with closing(sqlite3.connect(db_path, timeout=5)) as connection:
        with connection:
            connection.execute(
                "INSERT INTO guestbook_entries (name, message) VALUES (?, ?)",
                (name, message),
            )


def get_recent_entries(db_path: Path) -> list[tuple[int, str, str, str]]:
    """최신 글 50개를 ID 내림차순으로 읽는다."""
    with closing(sqlite3.connect(db_path, timeout=5)) as connection:
        return connection.execute(
            """
            SELECT id, name, message, created_at
            FROM guestbook_entries
            ORDER BY id DESC
            LIMIT ?
            """,
            (VISIBLE_ENTRY_LIMIT,),
        ).fetchall()


class GuestbookHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], db_path: Path) -> None:
        initialize_database(db_path)
        self.db_path = db_path
        super().__init__(address, GuestbookRequestHandler)


class GuestbookRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if urlsplit(self.path).path != "/":
            self.send_error(404, "페이지를 찾을 수 없습니다.")
            return

        entries = get_recent_entries(self.server.db_path)
        query = parse_qs(urlsplit(self.path).query)
        notice = (
            '<p class="notice" role="status">방명록을 저장했습니다.</p>'
            if query.get("added") == ["1"]
            else ""
        )
        self._send_page(200, self._render_page(entries, notice))

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/":
            self.send_error(404, "페이지를 찾을 수 없습니다.")
            return

        content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
        if content_type.strip().lower() != "application/x-www-form-urlencoded":
            self._show_error(400, "폼 형식의 요청만 받을 수 있습니다.")
            return

        content_length = self.headers.get("Content-Length")
        try:
            body_length = int(content_length or "")
        except ValueError:
            self._show_error(400, "요청 본문 크기를 확인할 수 없습니다.")
            return

        if body_length < 0 or body_length > MAX_FORM_BYTES:
            self._show_error(413, "입력한 내용이 너무 큽니다.")
            return

        try:
            form = parse_qs(
                self.rfile.read(body_length).decode("utf-8"),
                keep_blank_values=True,
            )
        except UnicodeDecodeError:
            self._show_error(400, "입력은 UTF-8 형식이어야 합니다.")
            return

        name = form.get("name", [""])[0].strip()
        message = form.get("message", [""])[0].strip()
        if not name or len(name) > MAX_NAME_LENGTH:
            self._show_error(400, f"이름은 1~{MAX_NAME_LENGTH}자로 입력해 주세요.")
            return
        if not message or len(message) > MAX_MESSAGE_LENGTH:
            self._show_error(
                400,
                f"내용은 1~{MAX_MESSAGE_LENGTH}자로 입력해 주세요.",
            )
            return

        add_entry(self.server.db_path, name, message)
        self.send_response(303)
        self.send_header("Location", "/?added=1")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _show_error(self, status: int, message: str) -> None:
        error_markup = f'<p class="error" role="alert">{escape(message)}</p>'
        self._send_page(status, self._render_page([], error_markup))

    def _render_page(
        self,
        entries: list[tuple[int, str, str, str]],
        notice: str,
    ) -> str:
        if entries:
            entry_markup = "\n".join(
                (
                    '<article class="entry">'
                    f"<h2>{escape(name)}</h2>"
                    f'<time datetime="{escape(created_at, quote=True)}">{escape(created_at)}</time>'
                    f'<p class="message">{escape(message)}</p>'
                    "</article>"
                )
                for _entry_id, name, message, created_at in entries
            )
        else:
            entry_markup = '<p class="empty">아직 등록된 글이 없습니다. 첫 글을 남겨보세요.</p>'

        template = HTML_PATH.read_text(encoding="utf-8")
        return (
            template.replace("{{notice}}", notice)
            .replace("{{entries}}", entry_markup)
        )

    def _send_page(self, status: int, content: str) -> None:
        encoded = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)


def create_server(
    db_path: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> GuestbookHTTPServer:
    """테스트와 실행 코드에서 같은 서버 생성을 사용한다."""
    return GuestbookHTTPServer((host, port), db_path)


def main() -> None:
    db_path = Path(
        os.environ.get("GUESTBOOK_DB_PATH", str(BASE_DIR / "guestbook.sqlite3"))
    )
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    server = create_server(db_path, host, port)
    print(f"방명록 서버 실행: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n방명록 서버를 종료합니다.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
