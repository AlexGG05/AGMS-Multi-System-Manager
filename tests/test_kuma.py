import unittest
from unittest.mock import patch
from fastapi import HTTPException
import test_admin_tickets as foundation
from app import main, kuma

class KumaTest(unittest.TestCase):
    setUp = foundation.AdminTicketsTest.setUp
    tearDown = foundation.AdminTicketsTest.tearDown
    login = foundation.AdminTicketsTest.login

    def test_personal_config_validation_and_csrf(self):
        self.assertEqual(self.client.get('/api/kuma').status_code,401)
        self.login('user@example.test')
        headers={'Origin': main.ORIGIN,'X-CSRF-Token':'test-csrf'}
        entry={'title':'Hosts','category':'vHosts','url':'https://status.example/status/main','monitors':['12']}
        self.assertEqual(self.client.put('/api/kuma',json={'entries':[entry]}).status_code,403)
        self.assertEqual(self.client.put('/api/kuma',json={'entries':[entry]},headers=headers).status_code,200)
        self.assertEqual(self.client.get('/api/kuma').json()['entries'],[entry])
        self.login('premium@example.test')
        self.assertEqual(self.client.get('/api/kuma').json()['entries'],[])
        for url in ['javascript:alert(1)','https://user:secret@example/status/main','https://example/status/main?x=1','http://[broken','https://example:22/status/main']:
            self.assertEqual(self.client.put('/api/kuma',json={'entries':[{**entry,'url':url}]},headers=headers).status_code,400)

    def test_optional_header_monitor_persistence_and_validation(self):
        self.login('user@example.test')
        headers={'Origin':main.ORIGIN,'X-CSRF-Token':'test-csrf'}
        entry={'title':'Hosts','category':'Hosts','url':'https://status.example/status/main','monitors':['12','13'],'header_monitor':'12'}
        self.assertEqual(self.client.put('/api/kuma',json={'entries':[entry]},headers=headers).status_code,200)
        self.assertEqual(self.client.get('/api/kuma').json()['entries'],[entry])
        for value in [12,{},'abc','1 OR 1=1','']:
            response=self.client.put('/api/kuma',json={'entries':[{**entry,'header_monitor':value}]},headers=headers)
            self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.get('/api/kuma').json()['entries'],[entry])
        custom={k:v for k,v in entry.items() if k!='header_monitor'}
        self.assertEqual(self.client.put('/api/kuma',json={'entries':[custom]},headers=headers).status_code,200)
        self.assertEqual(self.client.get('/api/kuma').json()['entries'],[custom])

    def test_kuma_groups_latest_heartbeat_and_unknown(self):
        with patch('app.kuma.public_json',side_effect=[{'publicGroupList':[{'name':'Hosts','monitorList':[{'id':12,'name':'Host A'},{'id':13,'name':'Host B'}]}]},{'heartbeatList':{'12':[{'status':0},{'status':1,'time':'now'}]},'uptimeList':{'12_24':0.99}}]):
            data=kuma.read_page('https://status.example/status/main')
        self.assertEqual(data['monitors'][0],{'id':'12','name':'Host A','group':'Hosts','status':'online','time':'now','uptime':0.99,'heartbeats':[{'status':'offline','time':None,'ping':None},{'status':'online','time':'now','ping':None}]})
        self.assertEqual(data['monitors'][1]['status'],'unknown')
        self.assertEqual(data['monitors'][1]['heartbeats'],[])

    def test_private_dns_blocked_before_socket_and_redirect_rejected(self):
        url,_,_=kuma.source('https://status.example/status/main')
        with patch('app.kuma.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),patch('app.kuma.socket.socket') as sock:
            with self.assertRaises(ValueError):kuma.public_json(url,'/api/status-page/main')
            sock.assert_not_called()
        with patch('app.kuma.public_json',side_effect=ValueError('redirect')):
            with self.assertRaises(HTTPException) as error:kuma.read_page('https://status.example/status/main')
            self.assertEqual(error.exception.status_code,502)

    def test_recent_heartbeats_are_bounded_and_not_replaced_with_local_samples(self):
        beats=[{'status':i%5,'time':str(i),'ping':float('nan') if i==119 else i} for i in range(120)]
        with patch('app.kuma.public_json',side_effect=[{'publicGroupList':[{'name':'Group','monitorList':[{'id':1,'name':'Service'}]}]},{'heartbeatList':{'1':beats},'uptimeList':{}}]):
            monitor=kuma.read_page('https://status.example/status/main')['monitors'][0]
        self.assertEqual(len(monitor['heartbeats']),100)
        self.assertEqual(monitor['heartbeats'][0]['time'],'20')
        self.assertEqual(monitor['heartbeats'][-1]['time'],'119')
        self.assertEqual(monitor['heartbeats'][-1]['status'],'unknown')
        self.assertIsNone(monitor['heartbeats'][-1]['ping'])
        self.assertIsNone(monitor['uptime'])
