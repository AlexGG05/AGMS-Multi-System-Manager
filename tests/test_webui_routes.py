import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault('SESSION_SECRET', 'test-session-secret-that-is-long-enough')
os.environ.setdefault('ADMIN_PASSWORD', 'test-admin-password-long-enough')
os.environ.setdefault('ADMIN_USERNAME', 'admin@example.test')
os.environ.setdefault('PUBLIC_ORIGIN', 'http://testserver')
from fastapi.testclient import TestClient
from app import main


class WebUiRoutesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_db = main.DB
        main.DB = str(Path(self.tmp.name) / 'webui.sqlite3')
        self.client = TestClient(main.app)
        self.client.__enter__()
        with main.connect() as db:
            db.execute("INSERT INTO workspaces(id,name,owner) VALUES ('webui-test','Test',?)", (main.ADMIN,))
            db.execute("INSERT INTO workspace_members(workspace_id,username,role) VALUES ('webui-test',?,'owner')", (main.ADMIN,))
            db.execute("INSERT INTO workspace_members(workspace_id,username,role) VALUES ('webui-test','viewer','viewer')")
            for ident, mode, minimum in [('arcane','embed','viewer'), ('bookstack','proxy','editor')]:
                db.execute("INSERT INTO workspace_navigation(id,workspace_id,title,icon,url,open_mode,min_role) VALUES (?,'webui-test',?,'globe','https://example.test/',?,?)", (ident,ident,mode,minimum))

    def tearDown(self):
        self.client.__exit__(None, None, None)
        main.DB = self.previous_db
        self.tmp.cleanup()

    def login(self, username):
        self.client.cookies.set('session', main.serializer.dumps({'u': username}))

    def test_anonymous_link_shows_login_and_preserves_service_after_login(self):
        response=self.client.get('/webui/webui-test/arcane/')
        self.assertEqual(response.status_code,200)
        self.assertIn('loginForm',response.text)
        self.assertIn("location.pathname.startsWith('/webui/')",response.text)

    def test_member_routes_serve_dashboard_and_enforce_item_permissions(self):
        self.login(main.ADMIN)
        for item in ['arcane','bookstack']:
            response=self.client.get('/webui/webui-test/'+item+'/')
            self.assertEqual(response.status_code,200)
            self.assertIn('passwordManagerSetup',response.text)
            self.assertIn('Cache-Control',response.headers)
        self.assertEqual(self.client.get('/webui/webui-test/missing/').status_code,404)
        self.login('viewer')
        self.assertEqual(self.client.get('/webui/webui-test/arcane/').status_code,200)
        self.assertEqual(self.client.get('/webui/webui-test/bookstack/').status_code,404)
        self.login('outsider')
        self.assertEqual(self.client.get('/webui/webui-test/arcane/').status_code,404)


if __name__ == '__main__':
    unittest.main()
