"""기존 SQLite의 ID/시각/댓글 관계를 빈 PostgreSQL 테이블로 복사한다."""
import argparse
from pathlib import Path
import sqlite3

from app import DatabaseSettings, connect_database, initialize_database


def migrate(path: Path) -> int:
    # 원본은 읽기 전용으로 열며 존재하지 않는 파일을 생성하지 않는다.
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as source:
        columns = {row[1] for row in source.execute('PRAGMA table_info(guestbook_entries)')}
        parent_column = 'parent_id' if 'parent_id' in columns else 'NULL'
        rows = source.execute(
            'SELECT id, name, message, created_at, ' + parent_column +
            ' FROM guestbook_entries ORDER BY id'
        ).fetchall()
    settings = DatabaseSettings.from_env()
    initialize_database(settings)
    with connect_database(settings) as target:
        target.execute('LOCK TABLE guestbook_entries IN ACCESS EXCLUSIVE MODE')
        if target.execute('SELECT 1 FROM guestbook_entries LIMIT 1').fetchone():
            raise ValueError('대상 DB가 비어 있지 않습니다. 중복/덮어쓰기를 방지하기 위해 중단합니다.')
        for row in rows:
            target.execute(
                'INSERT INTO guestbook_entries (id, name, message, created_at, parent_id) '
                'VALUES (%s, %s, %s, %s, %s)', row,
            )
        # ALTER SEQUENCE RESTART는 INSERT와 함께 롤백되며 다음 ID 충돌을 방지한다.
        next_id = max(1, max((row[0] for row in rows), default=0) + 1)
        from psycopg import sql
        target.execute(sql.SQL('ALTER TABLE guestbook_entries ALTER COLUMN id RESTART WITH {}').format(sql.Literal(next_id)))
    return len(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sqlite_file', type=Path)
    args = parser.parse_args()
    print(f'{migrate(args.sqlite_file)}개 글/댓글 이전 완료')
