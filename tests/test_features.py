import base64
import unittest
import os
import threading
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
import test_admin_tickets as foundation
from app import main, features

PNG = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'fixture').decode()


class FeaturesTest(unittest.TestCase):
    setUp = foundation.AdminTicketsTest.setUp
    tearDown = foundation.AdminTicketsTest.tearDown
    login = foundation.AdminTicketsTest.login
    post = foundation.AdminTicketsTest.post

    def seed_services(self):
        with main.connect() as db:
            db.execute("INSERT INTO workspaces(id,name,owner) VALUES ('shared','Shared',?)",(main.ADMIN,))
            db.execute("INSERT INTO workspace_members VALUES ('shared',?,'owner')",(main.ADMIN,))
            db.execute("INSERT INTO workspace_members VALUES ('shared','user@example.test','viewer')")
            for ident, minimum, url in [('public','viewer','http://public.example/'),('restricted','editor','https://restricted.example/'),('group','viewer',None)]:
                db.execute("INSERT INTO workspace_navigation(id,workspace_id,title,icon,url,min_role) VALUES (?,'shared',?,'globe',?,?)",(ident,ident,url,minimum))

    def headers(self):
        return {'Origin':main.ORIGIN,'X-CSRF-Token':'test-csrf'}

    def test_service_ticket_assignment_and_accessible_search(self):
        self.seed_services();self.login('user@example.test')
        services=self.client.get('/api/services').json()['services']
        self.assertEqual([s['id'] for s in services],['public'])
        created=self.post({'subject':'Public issue','category':'problem','priority':'high','workspace_id':'shared','service_id':'public'})
        self.assertEqual(created.status_code,201)
        ident=created.json()['id'];path='/api/tickets/'+ident
        ticket=self.client.get(path).json()['ticket']
        self.assertEqual(ticket['priority'],'high');self.assertEqual(ticket['service_title'],'public')
        self.assertEqual(self.post({'subject':'Forbidden','category':'problem','workspace_id':'shared','service_id':'restricted'}).status_code,404)
        self.assertEqual(self.post({'subject':'Invalid','category':'problem','priority':[]}).status_code,400)
        matches=self.client.get('/api/search',params={'q':'public'}).json()['results']
        self.assertEqual({r['type'] for r in matches},{'service','ticket'})
        self.assertEqual(self.client.get('/api/search',params={'q':'#'+str(created.json()['number'])}).json()['results'][0]['id'],ident)
        self.assertEqual(self.client.get('/api/search',params={'q':'restricted'}).json()['results'],[])
        unicode_ticket=self.post({'subject':'Änderung in Straße','category':'idea'}).json()['id']
        for query in ['änderung','strasse']:
            self.assertEqual(self.client.get('/api/search',params={'q':query}).json()['results'][0]['id'],unicode_ticket)
        self.login('premium@example.test')
        self.assertEqual(self.client.get('/api/search',params={'q':'Public'}).json()['results'],[])
        self.assertEqual(self.client.get('/api/services').json()['services'],[])
        self.login(main.ADMIN)
        self.assertEqual(self.client.put('/api/admin/tickets/'+ident+'/metadata',headers=self.headers(),json={'priority':'urgent','assigned_to':'second-admin@example.test'}).status_code,200)
        self.assertEqual(self.client.get(path).json()['ticket']['assigned_to'],'second-admin@example.test')
        self.assertEqual(self.client.put('/api/admin/tickets/'+ident+'/metadata',headers=self.headers(),json={'priority':'urgent','assigned_to':'user@example.test'}).status_code,400)
        self.login('user@example.test')
        self.assertEqual(self.client.put('/api/admin/tickets/'+ident+'/metadata',headers=self.headers(),json={'priority':'low','assigned_to':None}).status_code,403)

    def test_screenshots_are_atomic_and_permission_protected(self):
        self.login('user@example.test')
        ident=self.post({'subject':'Screenshot','category':'problem','attachments':[{'filename':'screen.png','data':PNG}]}).json()['id']
        detail=self.client.get('/api/tickets/'+ident).json()
        attachment=detail['attachments'][0];self.assertNotIn('content',attachment)
        url='/api/tickets/'+ident+'/attachments/'+attachment['id']
        response=self.client.get(url)
        self.assertEqual(response.status_code,200);self.assertEqual(response.content,base64.b64decode(PNG));self.assertEqual(response.headers['x-content-type-options'],'nosniff')
        self.assertIn('attachment;',response.headers['content-disposition'])
        self.login('premium@example.test');self.assertEqual(self.client.get(url).status_code,404)
        self.login(main.ADMIN);self.assertEqual(self.client.get(url).status_code,200)
        self.client.cookies.clear();self.assertEqual(self.client.get(url).status_code,401)
        self.login('user@example.test')
        count=len(self.client.get('/api/tickets').json()['tickets'])
        for files in [[{'filename':'bad.svg','data':base64.b64encode(b'<svg onload="alert(1)">').decode()}], [{'filename':'bad.png','data':'!!!'}], [{'filename':'screen.png','data':PNG}]*4]:
            self.assertEqual(self.post({'subject':'Rejected','category':'problem','attachments':files}).status_code,400)
        large=base64.b64encode(b'\x89PNG\r\n\x1a\n'+b'x'*features.MAX_IMAGE).decode()
        self.assertEqual(self.post({'subject':'Rejected','category':'problem','attachments':[{'filename':'large.png','data':large}]}).status_code,413)
        self.assertEqual(len(self.client.get('/api/tickets').json()['tickets']),count)

    def test_preferences_filter_bell_and_mail_retries_without_losing_ticket(self):
        self.login(main.ADMIN)
        preferences=self.client.get('/api/notification-settings').json()['settings']
        self.assertTrue(preferences['ticket_bell']);self.assertFalse(preferences['ticket_email'])
        preferences.update(ticket_bell=False,ticket_email=True,email_language='de')
        self.assertEqual(self.client.put('/api/notification-settings',headers=self.headers(),json=preferences).status_code,200)
        self.assertEqual(self.client.put('/api/notification-settings',json=preferences).status_code,403)
        self.login('user@example.test')
        with patch('app.features.send_email',side_effect=HTTPException(503,'SMTP unavailable')):
            response=self.post({'subject':'Mail test','category':'idea'})
        self.assertEqual(response.status_code,201)
        with main.connect() as db:
            self.assertEqual(db.execute('SELECT attempts FROM notification_email_outbox').fetchone()[0],1)
            db.execute('UPDATE notification_email_outbox SET next_attempt_at=0')
        self.login(main.ADMIN)
        with patch('app.features.send_email') as send:
            self.assertEqual(self.client.get('/api/notifications').json()['notifications'],[])
            self.assertEqual(send.call_count,1)
            self.assertIn('Neues Ticket eingegangen',send.call_args.args[1])
        with main.connect() as db:
            self.assertIsNotNone(db.execute('SELECT sent_at FROM notification_email_outbox').fetchone()[0])
        preferences.update(ticket_bell=True,ticket_email=False)
        self.client.put('/api/notification-settings',headers=self.headers(),json=preferences)
        self.assertEqual(len(self.client.get('/api/notifications').json()['notifications']),1)

    def test_status_reports_http_failure_without_probing_private_addresses(self):
        self.seed_services();self.login('user@example.test')
        url='/api/workspaces/shared/status/public'
        sock=MagicMock();sock.recv.return_value=b'HTTP/1.1 503 Service Unavailable\r\n'
        with patch('app.workspaces.socket.getaddrinfo',return_value=[(None,None,None,None,('93.184.216.34',80))]),patch('app.workspaces.socket.create_connection',return_value=sock):
            result=self.client.get(url).json();self.assertEqual(result['status'],'degraded');self.assertEqual(result['http_status'],503)
            sock.recv.return_value=b'HTTP/1.1'
            self.assertEqual(self.client.get(url).json()['status'],'unknown')
        with patch('app.workspaces.socket.getaddrinfo',return_value=[(None,None,None,None,('127.0.0.1',80))]),patch('app.workspaces.socket.create_connection') as connect:
            self.assertEqual(self.client.get(url).json(),{'status':'unknown','reason':'private'});connect.assert_not_called()
        self.assertEqual(self.client.get('/api/workspaces/shared/status/restricted').status_code,404)

    def test_reply_screenshot_and_account_cleanup(self):
        self.login('user@example.test')
        prefs={**features.DEFAULT_PREFS,'ticket_email':True}
        self.client.put('/api/notification-settings',headers=self.headers(),json=prefs)
        ident=self.post({'subject':'Reply attachment','category':'problem'}).json()['id']
        path='/api/tickets/'+ident
        self.login(main.ADMIN)
        self.client.post(path+'/comments',headers=self.headers(),json={'comment':'Please send a screenshot'})
        with patch('app.features.send_email',side_effect=HTTPException(503,'SMTP unavailable')):
            self.client.put('/api/admin/tickets/'+ident+'/status',headers=self.headers(),json={'status':'waiting_for_feedback'})
        self.login('user@example.test')
        self.assertEqual(self.client.post(path+'/comments',headers=self.headers(),json={'comment':'Here is the screenshot','attachments':[{'filename':'reply.png','data':PNG}]}).status_code,201)
        attachment=self.client.get(path).json()['attachments'][0]['id']
        self.login(main.ADMIN)
        self.assertEqual(self.client.delete('/api/admin/accounts/user@example.test',headers=self.headers()).status_code,200)
        self.assertEqual(self.client.get(path+'/attachments/'+attachment).status_code,404)
        with main.connect() as db:
            for table in ['notification_email_outbox','notification_preferences','ticket_attachments']:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)

    def test_combined_ticket_update_is_atomic(self):
        self.login('user@example.test')
        ident=self.post({'subject':'Atomic update','category':'problem'}).json()['id']
        self.login(main.ADMIN)
        path='/api/admin/tickets/'+ident+'/status'
        body={'status':'waiting_for_feedback','priority':'high','assigned_to':'user@example.test','comment':'Please send more details','attachments':[{'filename':'image.png','data':PNG}]}
        self.assertEqual(self.client.put(path,headers=self.headers(),json=body).status_code,400)
        detail=self.client.get('/api/tickets/'+ident).json()
        self.assertEqual(detail['ticket']['priority'],'normal');self.assertEqual(detail['ticket']['status'],'open')
        self.assertEqual(detail['comments'],[]);self.assertEqual(detail['attachments'],[])
        body['assigned_to']='second-admin@example.test'
        self.assertEqual(self.client.put(path,headers=self.headers(),json=body).status_code,200)
        detail=self.client.get('/api/tickets/'+ident).json()
        self.assertEqual(detail['ticket']['priority'],'high');self.assertEqual(detail['ticket']['status'],'waiting_for_feedback')
        self.assertEqual(len(detail['comments']),1);self.assertEqual(len(detail['attachments']),1)
        self.login('user@example.test')
        self.assertEqual(self.client.get('/api/notifications').json()['notifications'][0]['ticket_comment'],'Please send more details')

    def test_queued_email_is_retried_without_new_http_requests(self):
        self.login(main.ADMIN)
        self.client.put('/api/notification-settings',headers=self.headers(),json={**features.DEFAULT_PREFS,'ticket_email':True})
        self.login('user@example.test')
        with patch('app.features.send_email',side_effect=HTTPException(503,'Temporary failure')):
            self.post({'subject':'Background retry','category':'idea'})
        with main.connect() as db:
            db.execute('UPDATE notification_email_outbox SET next_attempt_at=0')
        delivered=threading.Event()
        with patch.dict(os.environ,{'SMTP_PASSWORD':'test-placeholder'}),patch('app.features.EMAIL_POLL_INTERVAL',0.02),patch('app.features.send_email',side_effect=lambda *args:delivered.set()) as send:
            self.client.portal.call(main.stop_notification_worker)
            self.client.portal.call(main.start_notification_worker)
            self.assertTrue(delivered.wait(2),'The background worker did not retry the pending email')
            self.assertEqual(send.call_count,1)
            sent=False
            for _ in range(100):
                with main.connect() as db:
                    sent=db.execute('SELECT sent_at FROM notification_email_outbox').fetchone()[0] is not None
                if sent: break
                threading.Event().wait(0.01)
            self.assertTrue(sent,'Successful delivery was not recorded')
