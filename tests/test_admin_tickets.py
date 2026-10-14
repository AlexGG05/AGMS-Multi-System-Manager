import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('SESSION_SECRET', 'test-session-secret-that-is-long-enough')
os.environ.setdefault('ADMIN_PASSWORD', 'test-admin-password-long-enough')
os.environ.setdefault('ADMIN_USERNAME', 'admin@example.test')
os.environ.setdefault('PUBLIC_ORIGIN', 'http://testserver')
os.environ['COOKIE_SECURE'] = 'false'
from fastapi.testclient import TestClient
from app import main


class AdminTicketsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_db = main.DB
        main.DB = str(Path(self.tmp.name) / 'test.sqlite3')
        self.client = TestClient(main.app)
        self.client.__enter__()
        with main.connect() as db:
            for username, role in [('user@example.test', 'user'), ('premium@example.test', 'premium'), ('second-admin@example.test', 'admin')]:
                db.execute('INSERT INTO users VALUES (?,?)', (username, 'unused-test-hash'))
                db.execute('INSERT INTO account_profiles(username,email,role) VALUES (?,?,?)', (username, username, role))
                db.execute('INSERT INTO account_security(username,verified_at,tier) VALUES (?,unixepoch(),0)', (username,))

    def tearDown(self):
        self.client.__exit__(None, None, None)
        main.DB = self.previous_db
        self.tmp.cleanup()

    def login(self, username):
        self.client.cookies.set('session', main.serializer.dumps({'u': username}))
        self.client.cookies.set('csrf', 'test-csrf')

    def post(self, data, headers=None):
        return self.client.post('/api/tickets', json=data, headers=headers or {'Origin': main.ORIGIN, 'X-CSRF-Token': 'test-csrf'})

    def test_users_can_submit_all_categories_and_only_admins_can_read(self):
        for username in ['user@example.test', 'premium@example.test', main.ADMIN]:
            self.login(username)
            for category in ['problem', 'idea', 'wish', 'other']:
                self.assertEqual(self.post({'subject': '  A subject <script>  ', 'category': category}).status_code, 201)
            if username != main.ADMIN:
                for path in ['/api/admin/tickets', '/api/admin/accounts', '/api/admin/proxy-requests']:
                    self.assertEqual(self.client.get(path).status_code, 403)
        tickets = self.client.get('/api/admin/tickets').json()['tickets']
        self.assertEqual(len(tickets), 12)
        self.assertEqual(tickets[0]['subject'], 'A subject <script>')
        self.assertIn('created_at', tickets[0])
        # A second administrator is authorized by role, not configured username.
        self.login('second-admin@example.test')
        for path in ['/api/admin/tickets', '/api/admin/accounts', '/api/admin/proxy-requests']:
            self.assertEqual(self.client.get(path).status_code, 200)
        with sqlite3.connect(main.DB) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM support_tickets').fetchone()[0], 12)

    def test_authentication_csrf_and_input_validation(self):
        self.assertEqual(self.post({'subject': 'Test', 'category': 'problem'}).status_code, 401)
        self.assertEqual(self.client.get('/api/admin/tickets').status_code, 401)
        self.login('user@example.test')
        self.assertEqual(self.client.post('/api/tickets', content='{', headers={'Origin': main.ORIGIN, 'X-CSRF-Token': 'test-csrf', 'Content-Type': 'application/json'}).status_code, 400)
        for headers in [{'Origin': main.ORIGIN}, {'Origin': 'http://attacker.test', 'X-CSRF-Token': 'test-csrf'}]:
            self.assertEqual(self.post({'subject': 'Test', 'category': 'problem'}, headers).status_code, 403)
        for data in [{'subject': ' ', 'category': 'problem'}, {'subject': 'x'*201, 'category': 'problem'}, {'subject': 42, 'category': 'idea'}, {'subject': 'Test', 'category': 'invalid'}, {'subject': 'Test', 'category': []}, [], {}]:
            self.assertEqual(self.post(data).status_code, 400)
        self.assertEqual(self.post({'subject': 'x'*200, 'category': 'other'}).status_code, 201)

    def test_admin_roles_cannot_be_deleted_or_overwritten_by_tier_changes(self):
        self.login(main.ADMIN)
        headers = {'Origin': main.ORIGIN, 'X-CSRF-Token': 'test-csrf'}
        self.assertEqual(self.client.delete('/api/admin/accounts/second-admin@example.test', headers=headers).status_code, 400)
        self.assertEqual(self.client.put('/api/admin/accounts/second-admin@example.test/tier', headers=headers, json={'tier': 1}).status_code, 400)
        self.login('user@example.test')
        self.assertEqual(self.client.post('/api/admin/proxy-requests/decision', headers=headers, json={'origin': 'https://example.test', 'decision': 'approved'}).status_code, 403)

    def test_schema_initialization_is_repeatable(self):
        self.login('user@example.test')
        self.post({'subject': 'Persistent ticket', 'category': 'wish'})
        main.init()
        main.init()
        with main.connect() as db:
            self.assertEqual(db.execute('SELECT subject FROM support_tickets').fetchone()[0], 'Persistent ticket')


if __name__ == '__main__':
    unittest.main()
