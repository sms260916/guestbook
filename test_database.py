import os
import unittest
from unittest.mock import patch, MagicMock

import app


class DatabaseUnitTests(unittest.TestCase):
    def test_missing_environment_fails_without_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'DB_HOST'):
                app.DatabaseSettings.from_env()

    def test_separate_credentials_and_ssl(self):
        values = dict(DB_HOST='example.invalid', DB_PORT='5432', DB_NAME='postgres',
                      DB_USER='postgres.test', DB_PASSWORD="test-only:@/%'")
        with patch.dict(os.environ, values, clear=True):
            settings = app.DatabaseSettings.from_env()
        self.assertNotIn(values['DB_PASSWORD'], repr(settings))
        with patch('app.psycopg.connect') as connect:
            app.connect_database(settings)
        self.assertEqual(connect.call_args.kwargs['password'], values['DB_PASSWORD'])
        self.assertEqual(connect.call_args.kwargs['sslmode'], 'require')

    def test_invalid_port_and_insecure_ssl_are_rejected(self):
        values = dict(DB_HOST='example.invalid', DB_PORT='0', DB_NAME='postgres',
                      DB_USER='test', DB_PASSWORD='test-only')
        with patch.dict(os.environ, values, clear=True):
            with self.assertRaises(ValueError):
                app.DatabaseSettings.from_env()
            os.environ['DB_PORT'] = '5432'
            os.environ['DB_SSLMODE'] = 'disable'
            with self.assertRaises(ValueError):
                app.DatabaseSettings.from_env()

    def test_insert_uses_parameters_and_transaction_context(self):
        connection = MagicMock()
        with patch('app.connect_database') as connect:
            connect.return_value.__enter__.return_value = connection
            app.add_entry(object(), "O'Reilly", '한글 %s', None)
        query, values = connection.execute.call_args.args
        self.assertIn('VALUES (%s, %s, %s)', query)
        self.assertEqual(values, ("O'Reilly", '한글 %s', None))
        connect.return_value.__exit__.assert_called_once_with(None, None, None)

    def test_query_groups_roots_and_replies(self):
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = [
            (2, '원글', '내용', '2026-10-29 01:00:00', None, 2),
            (3, '댓글', '답글', '2026-10-29 01:01:00', 2, 2),
        ]
        with patch('app.connect_database') as connect:
            connect.return_value.__enter__.return_value = connection
            entries = app.get_recent_entries(object())
        self.assertEqual(entries[0].replies[0].parent_id, 2)
        self.assertEqual(connection.execute.call_args.args[1], (50,))


if __name__ == '__main__':
    unittest.main()
