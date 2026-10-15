import asyncio
import hashlib
import json
import unittest
from unittest.mock import patch
import asyncssh
import test_features as foundation
from app import main,remote_sessions,guacamole_protocol
from starlette.websockets import WebSocketDisconnect


class RemoteSessionsTest(unittest.TestCase):
    setUp=foundation.FeaturesTest.setUp
    tearDown=foundation.FeaturesTest.tearDown
    login=foundation.FeaturesTest.login
    seed_services=foundation.FeaturesTest.seed_services
    headers=foundation.FeaturesTest.headers

    def seed(self,kind='ssh'):
        self.seed_services();self.login(main.ADMIN)
        with main.connect() as db:db.execute('UPDATE workspace_navigation SET open_mode=?,url=? WHERE id=?',(kind,kind+'://connection','public'))
        self.key=asyncssh.generate_private_key('ssh-ed25519')
        self.body={'kind':kind,'host':'host.example','port':22 if kind=='ssh' else 3389,'username':'operator','password':'test-remote-password','fingerprint':self.key.get_fingerprint() if kind=='ssh' else ''}
        self.path='/api/workspaces/shared/remote/public'
        response=self.client.put(self.path,json=self.body,headers=self.headers());self.assertEqual(response.status_code,200,response.text)
        with main.connect() as db:db.execute('INSERT INTO remote_targets VALUES(?,?,?,?,?)',(kind,'host.example',self.body['port'],json.dumps(['192.168.20.10']),main.ADMIN))

    def test_additive_migration_preserves_legacy_navigation_and_users(self):
        self.seed_services();self.login(main.ADMIN)
        with main.connect() as db:
            before=[tuple(r) for r in db.execute('SELECT id,parent_id,title,url,position,min_role,open_mode,favorite,color,icon_url FROM workspace_navigation ORDER BY id')]
            hashes=[tuple(r) for r in db.execute('SELECT * FROM users ORDER BY username')]
            db.execute('ALTER TABLE workspace_navigation DROP COLUMN tile_width')
            db.execute('ALTER TABLE workspace_navigation DROP COLUMN tile_height')
            db.execute('ALTER TABLE workspaces DROP COLUMN layout_revision')
        main.init();main.init()
        with main.connect() as db:
            self.assertEqual(before,[tuple(r) for r in db.execute('SELECT id,parent_id,title,url,position,min_role,open_mode,favorite,color,icon_url FROM workspace_navigation ORDER BY id')])
            self.assertEqual(hashes,[tuple(r) for r in db.execute('SELECT * FROM users ORDER BY username')])
            self.assertEqual(set(tuple(r) for r in db.execute('SELECT tile_width,tile_height FROM workspace_navigation')),{(1,1)})
        self.assertEqual(self.client.get('/api/workspaces/shared').json()['workspace']['layout_revision'],0)

    def test_remote_credentials_encrypted_and_shared_by_permission_only(self):
        self.seed()
        with main.connect() as db:
            blob=db.execute('SELECT secret FROM remote_connections').fetchone()[0]
            self.assertNotIn(b'test-remote-password',blob)
        self.login('user@example.test')
        data=self.client.get(self.path)
        self.assertEqual(data.status_code,200);self.assertNotIn('password',data.text);self.assertNotIn('test-remote-password',data.text)
        self.assertEqual(self.client.put(self.path,json=self.body,headers=self.headers()).status_code,403)
        self.assertEqual(self.client.delete(self.path,headers=self.headers()).status_code,403)
        self.login('premium@example.test');self.assertEqual(self.client.get(self.path).status_code,404)
        self.login(main.ADMIN)
        self.assertEqual(self.client.put(self.path,json={**self.body,'password':''},headers=self.headers()).status_code,200)
        self.assertEqual(self.client.put(self.path,json={**self.body,'password':'','host':'other.example'},headers=self.headers()).status_code,400)
        self.assertEqual(self.client.put(self.path,json={**self.body,'fingerprint':''},headers=self.headers()).status_code,400)
        self.assertEqual(self.client.put(self.path,json=self.body).status_code,403)
        main.init();main.init()
        self.assertTrue(self.client.get(self.path).json()['configured'])

    def test_target_approval_requires_admin_and_blocks_metadata(self):
        self.seed();self.login('user@example.test')
        self.assertEqual(self.client.post('/api/remote/targets',json=self.body,headers=self.headers()).status_code,403)
        self.login(main.ADMIN)
        for address in ['127.0.0.1','::1','169.254.169.254','224.0.0.1','0.0.0.0']:
            with patch('app.remote_sessions.socket.getaddrinfo',return_value=[(2,1,6,'',(address,22))]):
                self.assertEqual(self.client.post('/api/remote/targets',json=self.body,headers=self.headers()).status_code,400)
        with patch('app.remote_sessions.socket.getaddrinfo',return_value=[(2,1,6,'',('10.0.0.8',22))]):
            self.assertEqual(self.client.post('/api/remote/targets',json=self.body,headers=self.headers()).status_code,200)
        self.client.request('DELETE','/api/remote/targets',json=self.body,headers=self.headers())
        self.assertEqual(self.client.post(self.path+'/sessions',headers=self.headers()).status_code,403)

    def test_tickets_bound_to_cookie_and_single_use_logout_revokes(self):
        self.seed();response=self.client.post(self.path+'/sessions',headers=self.headers());self.assertEqual(response.status_code,200,response.text);ticket=response.json()['ticket']
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('/api/remote/tunnel?ticket='+ticket,headers={'Origin':'https://attacker.example'}):pass
        self.login('user@example.test')
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('/api/remote/tunnel?ticket='+ticket,headers={'Origin':main.ORIGIN}):pass
        self.login(main.ADMIN)
        response=self.client.post('/api/logout',headers=self.headers());self.assertEqual(response.status_code,200)
        with main.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM remote_sessions').fetchone()[0],0)

    def test_session_limits_and_minimum_tile_role(self):
        self.seed();self.login('user@example.test')
        for _ in range(remote_sessions.SESSION_LIMIT):self.assertEqual(self.client.post(self.path+'/sessions',headers=self.headers()).status_code,200)
        self.assertEqual(self.client.post(self.path+'/sessions',headers=self.headers()).status_code,429)
        with main.connect() as db:db.execute("UPDATE workspace_navigation SET min_role='editor' WHERE id='public'")
        self.assertEqual(self.client.post(self.path+'/sessions',headers=self.headers()).status_code,404)

    def test_editor_cannot_erase_or_modify_hidden_owner_tiles(self):
        self.seed()
        with main.connect() as db:
            db.execute("UPDATE workspace_members SET role='editor' WHERE workspace_id='shared' AND username='user@example.test'")
            db.execute("UPDATE workspace_navigation SET min_role='owner' WHERE id='public'")
        self.login('user@example.test');page=self.client.get('/api/workspaces/shared').json()
        self.assertNotIn('public',[x['id'] for x in page['navigation']])
        response=self.client.put('/api/workspaces/shared/navigation',json={'items':page['navigation'],'revision':page['workspace']['layout_revision']},headers=self.headers());self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.put('/api/workspaces/shared/navigation',json={'items':[{'id':'public','title':'Escalate','url':'https://example.com','min_role':'viewer'}]},headers=self.headers()).status_code,403)
        self.login(main.ADMIN)
        self.assertTrue(self.client.get(self.path).json()['configured'])
        page=self.client.get('/api/workspaces/shared').json()
        self.assertEqual(next(x for x in page['navigation'] if x['id']=='public')['min_role'],'owner')

    def test_remote_edit_obeys_existing_tier_limits(self):
        self.seed()
        with main.connect() as db:
            db.execute("UPDATE workspaces SET owner='user@example.test' WHERE id='shared'")
            db.execute("UPDATE workspace_members SET role='owner' WHERE workspace_id='shared' AND username='user@example.test'")
            db.execute("INSERT INTO workspaces(id,name,owner,created_at) VALUES('older','Older','user@example.test',0)")
            db.execute("INSERT INTO workspace_members VALUES('older','user@example.test','owner')")
        self.login('user@example.test')
        self.assertFalse(self.client.get('/api/workspaces/shared').json()['editable'])
        self.assertEqual(self.client.put(self.path,json=self.body,headers=self.headers()).status_code,403)
        self.assertTrue(self.client.get(self.path).json()['configured'])
        # The existing tier downgrade policy retains read/use access to old homepages.
        self.assertEqual(self.client.post(self.path+'/sessions',headers=self.headers()).status_code,200)

    def test_rdp_pin_normalized_and_invalid_pin_rejected(self):
        self.seed('rdp')
        pin=':'.join(['AB']*32)
        saved=self.client.put(self.path,json={**self.body,'fingerprint':pin},headers=self.headers())
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(self.client.get(self.path).json()['fingerprint'],'ab'*32)
        self.assertEqual(self.client.put(self.path,json={**self.body,'fingerprint':'not-a-sha256-pin'},headers=self.headers()).status_code,400)

    def test_remote_attempt_rate_limit_survives_closed_sessions(self):
        self.seed()
        with main.connect() as db:
            db.executemany('INSERT INTO remote_session_attempts VALUES(?,unixepoch())',[(main.ADMIN,)]*20)
        self.assertEqual(self.client.post(self.path+'/sessions',headers=self.headers()).status_code,429)

    def test_rdp_live_tunnel_server_credentials_ping_and_opcode_filter(self):
        self.seed('rdp');received=[]
        async def fake(reader,writer):
            try:
                received.append(await guacamole_protocol.read_instruction(reader))
                writer.write(guacamole_protocol.instruction('args','VERSION_1_5_0','hostname','port','username','password','ignore-cert'));await writer.drain()
                for _ in range(5):received.append(await guacamole_protocol.read_instruction(reader))
                writer.write(guacamole_protocol.instruction('ready','rdp-fixture'));writer.write(guacamole_protocol.instruction('size',0,640,480));await writer.drain()
                while True:received.append(await guacamole_protocol.read_instruction(reader))
            except (asyncio.IncompleteReadError,ConnectionError):pass
            finally:writer.close();await writer.wait_closed()
        async def start():return await asyncio.start_server(fake,'127.0.0.1',0)
        server=self.client.portal.call(start)
        try:
            port=server.sockets[0].getsockname()[1]
            with patch.dict('os.environ',{'GUACD_HOST':'127.0.0.1','GUACD_PORT':str(port)}):
                ticket=self.client.post(self.path+'/sessions',headers=self.headers()).json()['ticket']
                with self.client.websocket_connect('/api/remote/tunnel?ticket='+ticket,headers={'Origin':main.ORIGIN},subprotocols=['guacamole']) as ws:
                    self.assertEqual(ws.accepted_subprotocol,'guacamole')
                    self.assertIn('rdp-fixture',ws.receive_text());self.assertIn('size',ws.receive_text())
                    ws.send_text('0.,4.ping,3.123;');self.assertEqual(ws.receive_text(),'0.,4.ping,3.123;')
                    with main.connect() as db:db.execute("DELETE FROM remote_targets WHERE kind='rdp'")
                    # Check a rejected connection-selection instruction never reaches guacd.
                    ws.send_text('6.select,3.rdp;');self.assertIn('error',ws.receive_text())
            self.assertEqual(received[-1],['connect','VERSION_1_5_0','192.168.20.10','3389','operator','test-remote-password','false'])
        finally:server.close();self.client.portal.call(server.wait_closed)

    def test_optimistic_revision_and_tile_dimensions_preserve_connections(self):
        self.seed();initial=self.client.get('/api/workspaces/shared').json();items=initial['navigation'];revision=initial['workspace']['layout_revision']
        items[0]['tile_width']=2;items[0]['tile_height']=3
        saved=self.client.put('/api/workspaces/shared/navigation',json={'items':items,'revision':revision},headers=self.headers());self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(self.client.put('/api/workspaces/shared/navigation',json={'items':items,'revision':revision},headers=self.headers()).status_code,409)
        self.assertTrue(self.client.get(self.path).json()['configured'])
        current=self.client.get('/api/workspaces/shared').json();self.assertEqual(current['navigation'][0]['tile_width'],2)
        self.assertEqual(self.client.put('/api/workspaces/shared/navigation',json={'items':[{**items[0],'tile_width':99}]},headers=self.headers()).status_code,400)
        self.login('user@example.test');self.assertEqual(self.client.put('/api/workspaces/shared/navigation',json={'items':items},headers=self.headers()).status_code,403)

    def test_real_ssh_password_key_resize_host_pin_and_replay(self):
        self.seed()
        class Server(asyncssh.SSHServer):
            def begin_auth(self,user):return True
            def password_auth_supported(self):return True
            def public_key_auth_supported(self):return True
            def validate_password(self,user,password):return user=='operator' and password=='test-remote-password'
            def validate_public_key(self,user,key):return user=='operator' and key==client_key.convert_to_public()
        client_key=asyncssh.generate_private_key('ssh-ed25519')
        async def process(p):
            p.stdout.write(b'READY\r\n')
            while True:
                try:data=await p.stdin.readline()
                except asyncssh.TerminalSizeChanged:continue
                if not data:return
                p.stdout.write(b'ECHO:'+data)
        async def listen():return await asyncssh.create_server(Server,'127.0.0.1',0,server_host_keys=[self.key],process_factory=process,encoding=None)
        server=self.client.portal.call(listen)
        try:
            port=server.get_port()
            with main.connect() as db:
                db.execute('UPDATE remote_connections SET port=?',(port,));db.execute('UPDATE remote_targets SET port=?,addresses=?',(port,json.dumps(['127.0.0.1'])))
            self.body['port']=port
            with patch('app.remote_sessions.validate_address',side_effect=lambda a:a):
                for key_auth in [False,True,'encrypted']:
                    if key_auth:
                        passphrase='fixture-key-passphrase' if key_auth=='encrypted' else ''
                        response=self.client.put(self.path,json={**self.body,'password':'','private_key':client_key.export_private_key(passphrase=passphrase or None).decode(),'passphrase':passphrase},headers=self.headers());self.assertEqual(response.status_code,200,response.text)
                    ticket=self.client.post(self.path+'/sessions',headers=self.headers()).json()['ticket']
                    with self.client.websocket_connect('/api/remote/tunnel?ticket='+ticket,headers={'Origin':main.ORIGIN}) as ws:
                        self.assertIn(b'READY',ws.receive_bytes())
                        ws.send_json({'type':'resize','cols':120,'rows':40});ws.send_json({'type':'input','data':'hello\n'})
                        output=b''
                        while b'ECHO:hello' not in output:
                            message=ws.receive()
                            self.assertIn('bytes',message,message)
                            output+=message['bytes']
                        with self.assertRaises(WebSocketDisconnect):
                            with self.client.websocket_connect('/api/remote/tunnel?ticket='+ticket,headers={'Origin':main.ORIGIN}):pass
                with patch('app.remote_sessions.RECHECK_SECONDS',0.02):
                    ticket=self.client.post(self.path+'/sessions',headers=self.headers()).json()['ticket']
                    with self.client.websocket_connect('/api/remote/tunnel?ticket='+ticket,headers={'Origin':main.ORIGIN}) as ws:
                        self.assertIn(b'READY',ws.receive_bytes())
                        with main.connect() as db:db.execute('DELETE FROM workspace_members WHERE workspace_id=? AND username=?',('shared',main.ADMIN))
                        self.assertIn('error',ws.receive_json())
                    with main.connect() as db:db.execute("INSERT INTO workspace_members VALUES('shared',?,'owner')",(main.ADMIN,))
                # A different expected host key must fail closed, even with valid credentials.
                wrong=asyncssh.generate_private_key('ssh-ed25519').get_fingerprint()
                with main.connect() as db:db.execute('UPDATE remote_connections SET fingerprint=?',(wrong,))
                ticket=self.client.post(self.path+'/sessions',headers=self.headers()).json()['ticket']
                with self.client.websocket_connect('/api/remote/tunnel?ticket='+ticket,headers={'Origin':main.ORIGIN}) as ws:self.assertIn('error',ws.receive_json())
        finally:
            server.close();self.client.portal.call(server.wait_closed)


class GuacamoleProtocolTest(unittest.IsolatedAsyncioTestCase):
    async def test_handshake_supplies_server_credentials_and_keeps_tls_strict(self):
        received=[]
        async def fake(reader,writer):
            received.append(await guacamole_protocol.read_instruction(reader))
            writer.write(guacamole_protocol.instruction('args','VERSION_1_5_0','hostname','username','password','security','ignore-cert','cert-fingerprints'));await writer.drain()
            for _ in range(5):received.append(await guacamole_protocol.read_instruction(reader))
            writer.write(guacamole_protocol.instruction('ready','fixture-session'));await writer.drain();writer.close()
        server=await asyncio.start_server(fake,'127.0.0.1',0)
        try:
            reader,writer=await asyncio.open_connection('127.0.0.1',server.sockets[0].getsockname()[1])
            ident=await guacamole_protocol.handshake(reader,writer,{'port':3389,'username':'user','password':'fixture-secret','fingerprint':'ab'*32},'192.168.0.10',1280,720)
            self.assertEqual(ident,'fixture-session');self.assertEqual(received[-1],['connect','VERSION_1_5_0','192.168.0.10','user','fixture-secret','nla','false','sha256:'+':'.join(['ab']*32)])
            writer.close();await writer.wait_closed()
        finally:server.close();await server.wait_closed()

    async def test_guacamole_input_rejects_selection_and_bounds_resizing(self):
        self.assertEqual(guacamole_protocol.client_instruction(['size','99999','99999']),['size','3840','2160'])
        for args in [['select','rdp'],['connect','attacker'],['clipboard','0','text/plain'],['key','65','99'],['mouse','0','0','999'],['size','99999999999999999','2']]:
            with self.assertRaises(ValueError):guacamole_protocol.client_instruction(args)

    async def test_browser_protocol_parser_preserves_partial_frames(self):
        parser=guacamole_protocol.ClientParser()
        self.assertEqual(parser.feed('3.ke'),[])
        self.assertEqual(parser.feed('y,2.65,1.1;0.,4.ping,3.123;'),[['key','65','1'],['','ping','123']])
        with self.assertRaises(ValueError):parser.feed('bad.length;')

    async def test_protocol_unicode_and_size_limits(self):
        reader=asyncio.StreamReader();reader.feed_data(guacamole_protocol.instruction('test','ä😀'));reader.feed_eof()
        self.assertEqual(await guacamole_protocol.read_instruction(reader),['test','ä😀'])
        reader=asyncio.StreamReader();reader.feed_data(b'99999999.');reader.feed_eof()
        with self.assertRaises(ValueError):await guacamole_protocol.read_instruction(reader)
