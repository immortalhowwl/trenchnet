import tempfile
import unittest
from pathlib import Path
import telegram_bot as bot
from test_telegram_bot import W, snap


class ConsumerUITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'bot.sqlite')
        self.b = bot.Bot(self.path, clock=lambda: 1002)
        self.sent, self.answers = [], []
        self.uid = 0

    def tearDown(self):
        self.b.db.close()
        self.tmp.cleanup()

    def send(self, *args):
        self.sent.append(args)
        return True

    def callback(self, data, owner=1, chat=1, kind='private'):
        self.uid += 1
        self.b.updates([{'update_id': self.uid, 'callback_query': {
            'id': str(self.uid), 'from': {'id': owner}, 'data': data,
            'message': {'chat': {'id': chat, 'type': kind}}}}], self.send,
            answer=self.answers.append)

    def message(self, text):
        self.uid += 1
        self.b.updates([{'update_id': self.uid, 'message': {
            'chat': {'id': 1, 'type': 'private'}, 'text': text}}], self.send)

    def test_guided_inputs_survive_restart_cancel_and_do_not_opt_in(self):
        self.callback('add')
        self.assertIn('Send', self.sent[-1][1])
        self.b.db.close()
        self.b = bot.Bot(self.path, clock=lambda: 1003)
        self.message('invalid')
        self.assertIn('valid', self.sent[-1][1])
        self.message(W)
        self.assertIn('Following', self.sent[-1][1])
        self.assertFalse(self.b.state(1)['active'])
        self.callback('wallets')
        self.assertIn(W, self.sent[-1][1])
        self.callback('remove')
        self.message('/cancel')
        self.message(W)
        self.assertIn(W, self.b.command(1, '/status'))
        self.callback('remove')
        self.message(W)
        self.assertNotIn(W, self.b.command(1, '/status'))
        self.assertIsNone(self.b.pending(1))

    def test_feed_and_status_use_injected_source_without_subscribing(self):
        calls = []
        def source():
            calls.append(True)
            return snap()
        def request(text, source=source):
            self.uid += 1
            self.b.updates([{'update_id':self.uid, 'message': {
                'chat': {'id':1, 'type':'private'}, 'text':text}}], self.send, snapshot=source)
            return self.sent[-1][1]
        text = request('/feed')
        self.assertIn('BUY', text)
        self.assertIn(snap()['trades'][0]['timestamp'], text)
        self.assertIn('https://solscan.io/tx/', text)
        self.assertFalse(self.b.state(1)['active'])
        self.assertEqual(self.b.db.execute('SELECT count(*) FROM delivered').fetchone()[0], 0)
        self.assertIn('Source updated at:', request('/status'))
        self.assertEqual(len(calls), 2)
        partial = snap(); partial['status']['collector'] = 'partial'
        text = request('/feed', lambda: partial)
        self.assertIn('partial', text)
        self.assertNotIn('BUY', text)
        self.assertIn('stale', request('/feed', lambda: snap(1)))
        self.assertIn('unavailable', request('/status', lambda: None))
        self.assertIn('No eligible', request('/feed', lambda: dict(snap(), trades=[])))

    def test_transport_poll_and_callback_ack_serialization(self):
        import io
        import json
        calls = []
        class Opener:
            def open(self, req, timeout):
                calls.append((req.full_url.rsplit('/', 1)[-1], json.loads(req.data)))
                return io.BytesIO(b'{"ok":true,"result":[]}')
        transport = bot.Transport('123:FAKE', opener=Opener())
        transport.poll(5)
        self.assertIn('callback_query', calls[-1][1]['allowed_updates'])
        self.assertTrue(transport.answer('callback-id'))
        self.assertEqual(calls[-1], ('answerCallbackQuery', {'callback_query_id':'callback-id'}))
        self.assertIsNone(transport.telegram('deleteMessage', {}))

    def test_pause_committed_before_callback_ack_failure(self):
        self.b.command(1, '/subscribe')
        observed = []
        def fail_ack(_):
            observed.append((self.b.state(1)['active'], self.b.offset()))
            raise OSError('unavailable')
        self.b.updates([{'update_id':10, 'callback_query': {
            'id':'cb', 'from': {'id':1}, 'data':'pause',
            'message': {'chat': {'id':1,'type':'private'}}}}], self.send, answer=fail_ack)
        self.assertEqual(observed, [(0,11)])
        self.assertIn('OFF', self.sent[-1][1])

    def test_additive_upgrade_preserves_existing_state(self):
        import sqlite3
        self.b.db.close()
        with sqlite3.connect(self.path) as db:
            db.execute('DROP TABLE inputs')
            db.execute('INSERT INTO recipients VALUES(1,1,900)')
            db.execute('INSERT INTO follows VALUES(1,?,901)', (W,))
            db.execute("INSERT INTO delivered VALUES(1,'old-event')")
            db.execute("INSERT INTO state VALUES('offset',42)")
        self.b = bot.Bot(self.path, clock=lambda:1002)
        self.assertEqual(self.b.state(1)['since'], 900)
        self.assertEqual(self.b.state(1)['active'], 1)
        self.assertEqual(self.b.offset(), 42)
        self.assertEqual(self.b.db.execute('SELECT event FROM delivered').fetchone()[0], 'old-event')
        self.assertIn(W, self.b.command(1, '/wallets'))
        self.b.command(1, '/follow')
        self.assertEqual(self.b.pending(1), '/follow')

    def test_malformed_and_inline_callbacks_are_ignored(self):
        updates = [{'update_id':i, 'callback_query':cb} for i, cb in enumerate([
            {'id':'a','data':'enable','from':{'id':1}},
            {'id':'b','data':'enable','from':None,'message':{'chat':{'type':'private','id':1}}},
            {'id':'c','data':[], 'from':{'id':1}, 'message':None},
            {'id':'d','data':'enable','from':{'id':True},'message':{'chat':{'type':'private','id':1}}},
        ], 1)]
        self.b.updates(updates, self.send, answer=self.answers.append)
        self.assertIsNone(self.b.state(1))
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.answers), 4)

    def test_callback_ack_precedes_slow_source_lookup(self):
        def source():
            self.assertEqual(self.answers, ['feed-id'])
            return snap()
        self.b.updates([{'update_id':1,'callback_query': {
            'id':'feed-id','from':{'id':1},'data':'feed',
            'message':{'chat':{'type':'private','id':1}}}}], self.send,
            snapshot=source, answer=self.answers.append)
        self.assertIn('BUY', self.sent[-1][1])

    def test_menu_and_private_callback_opt_in(self):
        self.message('/start')
        self.assertIn('Enable alerts', str(self.sent[-1][2]))
        self.callback('enable', owner=2)
        self.callback('enable', kind='group')
        self.assertFalse(self.b.state(1)['active'])
        self.assertEqual(len(self.sent), 1)
        self.callback('enable')
        self.assertTrue(self.b.state(1)['active'])
        self.b.clock = lambda: 1010
        self.callback('enable')
        self.assertEqual(self.b.state(1)['since'], 1002)
        self.message('/start')
        self.assertTrue(self.b.state(1)['active'])
        self.callback('pause')
        self.assertFalse(self.b.state(1)['active'])
        self.assertEqual(len(self.answers), 5)
        self.callback('unknown')
        self.assertFalse(self.b.state(1)['active'])
