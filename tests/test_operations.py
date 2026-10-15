import json,time,unittest
from unittest.mock import patch
import test_features as foundation
from app import main,operations,push_channels,security_keys,public_net
from fastapi import HTTPException

class OperationsTest(unittest.TestCase):
    setUp=foundation.FeaturesTest.setUp
    tearDown=foundation.FeaturesTest.tearDown
    login=foundation.FeaturesTest.login
    seed_services=foundation.FeaturesTest.seed_services
    headers=foundation.FeaturesTest.headers

    def test_preferences_opt_in_and_widgets_are_private(self):
        self.seed_services();self.login('user@example.test')
        self.assertEqual(self.client.get('/api/account/preferences').json(),{'refresh_seconds':60,'widgets':[]})
        self.assertEqual(self.client.get('/api/account/profile').status_code,200)
        body={'refresh_seconds':30,'widgets':['tickets','status','expiry','proxmox','sabnzbd']}
        self.assertEqual(self.client.put('/api/account/preferences',json=body).status_code,403)
        self.assertEqual(self.client.put('/api/account/preferences',json=body,headers=self.headers()).status_code,200)
        self.assertEqual(self.client.put('/api/account/preferences',json={**body,'refresh_seconds':1},headers=self.headers()).status_code,400)
        widgets=self.client.get('/api/widgets').json()
        self.assertEqual(widgets['data']['status']['unknown'],1)
        self.assertIn('error',widgets['data']['proxmox'])
        self.assertIn('error',widgets['data']['sabnzbd'])
        self.login('premium@example.test');self.assertEqual(self.client.get('/api/account/preferences').json()['widgets'],[])

    def test_latest_service_checks_remain_private_without_history_api(self):
        self.seed_services();now=int(time.time())//60*60
        with main.connect() as db:
            db.execute('INSERT INTO service_history VALUES(?,?,?,?,NULL)',('shared','public',now-60,'offline'))
            operations.record(db,'shared','public',{'status':'online'})
            self.assertEqual(db.execute("SELECT count(*) FROM service_history WHERE workspace_id='shared'").fetchone()[0],1)
        self.login('user@example.test')
        data=self.client.get('/api/monitoring').json()
        self.assertEqual([s['id'] for s in data['services']],['public'])
        self.assertEqual(data['services'][0]['latest']['status'],'online')
        self.assertEqual(self.client.get('/api/monitoring/history/shared/public').status_code,404)
        self.login('premium@example.test');self.assertEqual(self.client.get('/api/monitoring').json()['services'],[])

    def test_dependency_acl_cycles_and_audit(self):
        self.seed_services()
        with main.connect() as db:
            db.execute("INSERT INTO workspace_navigation(id,workspace_id,title,icon,url,min_role) VALUES ('host','shared','Host','globe','https://host.example','viewer')")
        payload={'workspace_id':'shared','service_id':'public','depends_on':['host']}
        self.login('user@example.test');self.assertEqual(self.client.put('/api/monitoring/dependencies',json=payload,headers=self.headers()).status_code,403)
        self.login(main.ADMIN);self.assertEqual(self.client.put('/api/monitoring/dependencies',json=payload,headers=self.headers()).status_code,200)
        self.assertEqual(self.client.put('/api/monitoring/dependencies',json={**payload,'service_id':'host','depends_on':['public']},headers=self.headers()).status_code,400)
        self.assertEqual(self.client.put('/api/monitoring/dependencies',json={**payload,'depends_on':['nonexistent']},headers=self.headers()).status_code,404)
        self.assertEqual(self.client.get('/api/admin/audit/shared').json()['events'][0]['actor'],main.ADMIN)
        self.login('user@example.test');self.assertEqual(len(self.client.get('/api/monitoring').json()['dependencies']),1)
        self.assertEqual(self.client.get('/api/admin/audit').status_code,403)

    def test_audit_navigation_diff_actor_and_noop(self):
        self.seed_services();self.login(main.ADMIN)
        items=self.client.get('/api/workspaces/shared').json()['navigation']
        items[0]['title']='Renamed service'
        response=self.client.put('/api/workspaces/shared/navigation',json={'items':items},headers=self.headers());self.assertEqual(response.status_code,200,response.text)
        events=self.client.get('/api/admin/audit/shared').json()['events'];self.assertEqual(len(events),1)
        self.assertTrue(any(c['title']=='Renamed service' and 'title' in c['fields'] for c in events[0]['details']['changed']))
        self.assertEqual(events[0]['actor'],main.ADMIN)
        self.client.put('/api/workspaces/shared/navigation',json={'items':items},headers=self.headers())
        self.assertEqual(len(self.client.get('/api/admin/audit/shared').json()['events']),1)

    def test_expiry_watch_is_private_and_notifies_once(self):
        self.login('user@example.test')
        response=self.client.post('/api/monitoring/watches',json={'kind':'domain','value':'example.com','label':'Domain'},headers=self.headers())
        self.assertEqual(response.status_code,200);ident=response.json()['id']
        with patch('app.operations.check_watch',return_value=int(time.time())+86400):
            operations.check_due_watches(main.connect,'user@example.test');operations.check_due_watches(main.connect,'user@example.test')
        with main.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM workspace_notifications WHERE username=?',('user@example.test',)).fetchone()[0],1)
        self.login('premium@example.test');self.assertEqual(self.client.get('/api/monitoring').json()['watches'],[])
        self.client.delete('/api/monitoring/watches/'+ident,headers=self.headers())
        with main.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM expiry_watches').fetchone()[0],1)
        self.assertEqual(self.client.post('/api/monitoring/watches',json={'kind':'certificate','value':'http://example.com','label':'Bad'},headers=self.headers()).status_code,400)

    def test_push_encryption_masking_retry_and_disable(self):
        self.login('user@example.test')
        settings={'url':'https://ntfy.example/topic','token':'private-test-token','chat_id':''}
        self.assertEqual(self.client.put('/api/account/push/ntfy',json={'enabled':True,'settings':settings},headers=self.headers()).status_code,200)
        self.assertNotIn('private-test-token',self.client.get('/api/account/push').text)
        with main.connect() as db:
            stored=db.execute('SELECT settings FROM push_channels').fetchone()[0];self.assertNotIn(b'private-test-token',stored)
            db.execute("INSERT INTO workspace_notifications(id,username,message) VALUES ('push-note','user@example.test','Test')")
            push_channels.queue(db,'push-note','user@example.test')
        with patch('app.push_channels.send',side_effect=ValueError('offline')):push_channels.deliver(main.connect)
        with main.connect() as db:
            self.assertEqual(db.execute('SELECT attempts FROM push_outbox').fetchone()[0],1)
            db.execute('UPDATE push_outbox SET next_attempt_at=0')
        with patch('app.push_channels.send') as send:push_channels.deliver(main.connect);send.assert_called_once()
        with main.connect() as db:self.assertIsNotNone(db.execute('SELECT sent_at FROM push_outbox').fetchone()[0])
        self.assertEqual(self.client.put('/api/account/push/ntfy',json={'enabled':False,'keep_settings':True},headers=self.headers()).status_code,200)

    def test_public_request_blocks_dns_private_before_connect(self):
        with patch('app.public_net.socket.getaddrinfo',return_value=[(2,1,6,'',('10.0.0.2',443))]),patch('app.public_net.socket.socket') as sock:
            with self.assertRaises(ValueError):public_net.request('https://example.com')
            sock.assert_not_called()

    def test_totp_setup_login_replay_and_recovery(self):
        self.login(main.ADMIN)
        result=self.client.post('/api/account/security/totp/setup',json={'password':main.PASSWORD},headers=self.headers())
        self.assertEqual(result.status_code,200,result.text);secret=result.json()['secret'];step=int(time.time())//30
        qr=self.client.get('/api/account/security/totp/qr');self.assertEqual(qr.status_code,200);self.assertIn('no-store',qr.headers['cache-control'])
        self.assertEqual(self.client.post('/api/account/security/totp/enable',json={'code':'wrong'},headers=self.headers()).status_code,400)
        enabled=self.client.post('/api/account/security/totp/enable',json={'code':security_keys.totp(secret,step)},headers=self.headers())
        self.assertEqual(enabled.status_code,200);codes=enabled.json()['recovery_codes'];self.assertEqual(len(codes),10)
        self.client.cookies.clear();main.failures.clear()
        login={'username':main.ADMIN,'password':main.PASSWORD}
        pending=self.client.post('/api/login',json=login,headers={'Origin':main.ORIGIN});self.assertTrue(pending.json()['totp_required']);self.assertNotIn('session',self.client.cookies)
        self.assertEqual(self.client.post('/api/login',json={**login,'code':security_keys.totp(secret,step)},headers={'Origin':main.ORIGIN}).status_code,401)
        successful=self.client.post('/api/login',json={**login,'code':codes[0]},headers={'Origin':main.ORIGIN});self.assertEqual(successful.status_code,200)
        self.assertIn('session',self.client.cookies)
        self.assertEqual(self.client.post('/api/login',json={**login,'code':codes[0]},headers={'Origin':main.ORIGIN}).status_code,401)
        self.assertEqual(self.client.post('/api/account/security/totp/disable',json={'password':main.PASSWORD,'code':codes[1]},headers={'Origin':main.ORIGIN,'X-CSRF-Token':self.client.cookies.get('csrf')}).status_code,200)
        self.assertFalse(self.client.get('/api/account/security').json()['totp_enabled'])

    def test_passkey_challenge_one_use_and_verification_failure(self):
        self.login(main.ADMIN)
        result=self.client.post('/api/account/security/passkeys/options',json={'password':main.PASSWORD},headers=self.headers())
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['options']['authenticatorSelection']['userVerification'],'required')
        self.assertEqual(result.json()['options']['authenticatorSelection']['residentKey'],'required')
        body={'challenge_id':result.json()['challenge_id'],'credential':{},'name':'Test'}
        self.assertEqual(self.client.post('/api/account/security/passkeys',json=body,headers=self.headers()).status_code,400)
        self.assertEqual(self.client.post('/api/account/security/passkeys',json=body,headers=self.headers()).status_code,400)
        self.assertEqual(self.client.post('/api/auth/passkey/options',json={},headers={'Origin':'https://evil.test'}).status_code,403)
        challenge=self.client.post('/api/auth/passkey/options',json={},headers={'Origin':main.ORIGIN}).json()['challenge_id']
        self.assertEqual(self.client.post('/api/auth/passkey/verify',json={'challenge_id':challenge,'credential':{'id':'missing'}},headers={'Origin':main.ORIGIN}).status_code,401)

    def test_all_push_provider_requests_are_scoped_and_do_not_allow_mentions(self):
        examples={
          'ntfy':{'url':'https://ntfy.example/topic','token':'test-token','chat_id':''},
          'gotify':{'url':'https://gotify.example','token':'test-token','chat_id':''},
          'telegram':{'url':'','token':'12345:test-token','chat_id':'1234'},
          'discord':{'url':'https://discord.com/api/webhooks/123/test-token','token':'','chat_id':''}}
        for provider,settings in examples.items():
            settings=push_channels.validate(provider,settings)
            with patch('app.push_channels.public_net.request') as request:
                push_channels.send(provider,settings,'Test notification')
                self.assertEqual(request.call_args.args[1],'POST')
                if provider=='discord':self.assertEqual(request.call_args.args[2]['allowed_mentions'],{'parse':[]})
                if provider=='gotify':self.assertEqual(request.call_args.args[3]['X-Gotify-Key'],'test-token')
                if provider=='telegram':self.assertEqual(request.call_args.args[2]['chat_id'],'1234')
        with self.assertRaises(ValueError):push_channels.validate('discord',{'url':'https://evil.example/webhook'})

    def test_migration_preserves_existing_settings_and_credentials(self):
        self.login(main.ADMIN)
        result=self.client.post('/api/account/security/totp/setup',json={'password':main.PASSWORD},headers=self.headers())
        self.assertEqual(result.status_code,200)
        with main.connect() as db:
            before=db.execute('SELECT secret FROM account_factors WHERE username=?',(main.ADMIN,)).fetchone()[0]
            operations.record(db,'workspace','service',{'status':'online'})
        main.init();main.init()
        with main.connect() as db:
            self.assertEqual(db.execute('SELECT secret FROM account_factors WHERE username=?',(main.ADMIN,)).fetchone()[0],before)
            self.assertEqual(db.execute('SELECT count(*) FROM service_history').fetchone()[0],1)

    def test_existing_long_passwords_still_work_for_login_and_factor_setup(self):
        password='existing-long-password-'+('x'*80)
        with main.connect() as db:
            db.execute('UPDATE users SET password_hash=? WHERE username=?',(main.bcrypt.hashpw(password.encode(),main.bcrypt.gensalt(rounds=4)).decode(),'user@example.test'))
        main.failures.clear()
        response=self.client.post('/api/login',json={'username':'user@example.test','password':password},headers={'Origin':main.ORIGIN})
        self.assertEqual(response.status_code,200)
        response=self.client.post('/api/account/security/totp/setup',json={'password':password},headers={'Origin':main.ORIGIN,'X-CSRF-Token':self.client.cookies.get('csrf')})
        self.assertEqual(response.status_code,200)

    def test_de_domain_manual_renewal_preserved_and_scoped(self):
        with patch('app.operations.public_net.request') as request:
            with self.assertRaises(operations.NoPublicExpiry):operations.check_watch('domain','agrosskopf.de')
            request.assert_not_called()
        self.login('user@example.test')
        watch=self.client.post('/api/monitoring/watches',json={'kind':'domain','value':'agrosskopf.de','label':'Domain'},headers=self.headers()).json()['id']
        operations.check_due_watches(main.connect,'user@example.test')
        item=self.client.get('/api/monitoring').json()['watches'][0]
        self.assertIn('.de',item['error']);self.assertIsNone(item['expires_at'])
        self.assertEqual(self.client.put('/api/monitoring/watches/'+watch,json={'renewal_date':'2030-10-15'},headers=self.headers()).status_code,200)
        with patch('app.operations.check_watch') as check:
            operations.check_due_watches(main.connect,'user@example.test');check.assert_not_called()
        main.init()
        item=self.client.get('/api/monitoring').json()['watches'][0]
        self.assertEqual(item['expires_at'],item['manual_expires_at']);self.assertIsNone(item['error'])
        self.assertEqual(self.client.put('/api/monitoring/watches/'+watch,json={'renewal_date':'bad-date'},headers=self.headers()).status_code,400)
        self.login('premium@example.test')
        self.assertEqual(self.client.put('/api/monitoring/watches/'+watch,json={'renewal_date':'2031-01-01'},headers=self.headers()).status_code,404)
        self.login('user@example.test')
        self.assertEqual(self.client.put('/api/monitoring/watches/'+watch,json={'renewal_date':None},headers=self.headers()).status_code,200)

    def test_registry_missing_expiration_is_not_a_connection_error(self):
        with patch('app.operations.public_net.request',return_value={'events':[{'eventAction':'last changed','eventDate':'2025-01-01T00:00:00Z'}]}):
            with self.assertRaises(operations.NoPublicExpiry):operations.check_watch('domain','example.com')
