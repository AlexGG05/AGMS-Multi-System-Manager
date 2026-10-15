import unittest
from unittest.mock import patch, AsyncMock
import httpx
import test_webui_routes as foundation
from app import main

class ProxyPathsTest(unittest.TestCase):
    setUp=foundation.WebUiRoutesTest.setUp
    tearDown=foundation.WebUiRoutesTest.tearDown
    login=foundation.WebUiRoutesTest.login

    def test_start_path_saved_with_origin_only_approval(self):
        self.login(main.ADMIN);self.client.cookies.set('csrf','test-csrf')
        headers={'Origin':main.ORIGIN,'X-CSRF-Token':'test-csrf'}
        item={'id':'kuma','title':'Kuma','url':'https://example.test/dashboard?view=all','open_mode':'proxy','min_role':'viewer'}
        response=self.client.put('/api/workspaces/webui-test/navigation',json={'items':[item]},headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        with main.connect() as db:
            self.assertEqual(db.execute("SELECT url FROM workspace_navigation WHERE id='kuma'").fetchone()['url'],item['url'])
            self.assertIsNotNone(db.execute("SELECT 1 FROM proxy_requests WHERE origin='https://example.test'").fetchone())
        for url in ['http://example.test/dashboard','https://user:pass@example.test/dashboard','https://example.test/dashboard#fragment']:
            self.assertEqual(self.client.put('/api/workspaces/webui-test/navigation',json={'items':[{**item,'url':url}]},headers=headers).status_code,400)

    def test_proxy_routes_spa_base_and_keeps_upstream_paths(self):
        self.login(main.ADMIN)
        with main.connect() as db:
            db.execute("UPDATE workspace_navigation SET url='https://example.test/dashboard' WHERE id='bookstack'")
            db.execute("INSERT INTO proxy_allowed_origins(origin,approved_by) VALUES ('https://example.test',?)",(main.ADMIN,))
        upstream=httpx.Response(200,text='<html><head><base href="/"><script src="/assets/app.js"></script></head><body></body></html>',headers={'content-type':'text/html'})
        with patch('app.web_proxy.socket.getaddrinfo',return_value=[(2,1,6,'',('93.184.216.34',443))]),patch('app.web_proxy.httpx.AsyncClient') as client:
            request=AsyncMock(return_value=upstream);client.return_value.__aenter__.return_value.request=request
            response=self.client.get('/web-proxy/webui-test/bookstack/dashboard?view=all')
            self.assertEqual(response.status_code,200)
            self.assertEqual(request.call_args.args[1],'https://example.test/dashboard?view=all')
            self.assertEqual(response.text.count('<base '),1)
            self.assertIn('<base href="/web-proxy/webui-test/bookstack/">',response.text)
            self.assertLess(response.text.index('<base '),response.text.index('/assets/app.js'))
            self.assertIn('src="/web-proxy/webui-test/bookstack/assets/app.js"',response.text)
            self.client.get('/web-proxy/webui-test/bookstack/assets/app.js')
            self.assertEqual(request.call_args.args[1],'https://example.test/assets/app.js')
        self.login('viewer')
        self.assertEqual(self.client.get('/web-proxy/webui-test/bookstack/dashboard').status_code,404)

    def test_sabnzbd_relative_login_form_preserves_session(self):
        self.client.base_url='https://testserver'
        self.login(main.ADMIN)
        with main.connect() as db:
            db.execute("INSERT INTO proxy_allowed_origins(origin,approved_by) VALUES ('https://example.test',?)",(main.ADMIN,))
        calls=[]
        async def upstream(method,target,**kwargs):
            calls.append((method,target,kwargs))
            if method=='POST':
                self.assertEqual(target,'https://example.test/login/')
                return httpx.Response(302,headers=[('location','/'),('set-cookie','login_cookie=fixture-session; Path=/; HttpOnly'),('set-cookie','login_salt=123; Path=/; HttpOnly')])
            if target.endswith('/login/'):
                return httpx.Response(200,text='<html><head></head><body><form action="./" method="post"><button>Login</button></form></body></html>',headers={'content-type':'text/html'})
            self.assertEqual(kwargs['cookies'],{'login_cookie':'fixture-session','login_salt':'123'})
            self.assertNotIn('session',kwargs['cookies'])
            return httpx.Response(200,text='Authenticated SABnzbd fixture')
        with patch('app.web_proxy.socket.getaddrinfo',return_value=[(2,1,6,'',('93.184.216.34',443))]),patch('app.web_proxy.httpx.AsyncClient') as client:
            client.return_value.__aenter__.return_value.request=AsyncMock(side_effect=upstream)
            prefix='/web-proxy/webui-test/bookstack'
            page=self.client.get(prefix+'/login/')
            self.assertIn('action="./"',page.text)
            self.assertNotIn('<base ',page.text)
            response=self.client.post(prefix+'/login/',data={'username':'fixture','password':'fixture'},headers={'Origin':main.ORIGIN})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.text,'Authenticated SABnzbd fixture')
            self.assertEqual(len(calls),3)
            self.client.get(prefix+'/')
            self.assertEqual(len(calls),4)

    def test_relative_navigation_and_forms_remain_relative_without_injected_base(self):
        from app.web_proxy import rewrite_markup
        markup='<form action="./"><button formaction="../logout/">Logout</button></form><script src="./app.js"></script>'
        self.assertEqual(rewrite_markup(markup,'https://example.test','/web-proxy/ws/item'),markup)
