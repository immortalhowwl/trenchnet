import tempfile
import unittest
from pathlib import Path
import telegram_bot as bot

W = '11111111111111111111111111111111'

def snap(stamp=1001, **changes):
    from datetime import datetime, timezone
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
    trade = dict(id='1'*64+':17', signature='1'*64, wallet=W, mint=W,
                 timestamp=iso(stamp), verified=True, side='buy',
                 source='Pump TradeEvent / finalized Solana RPC')
    trade.update(changes)
    return dict(version='trenchnet-v1', updatedAt=iso(stamp), status={'collector':'ok'}, trades=[trade])

class BotTests(unittest.TestCase):
    def test_delivery_cutoffs_freshness_and_isolation(self):
        with tempfile.TemporaryDirectory() as d:
            b = bot.Bot(str(Path(d)/'b.db'), clock=lambda:1000)
            for chat in (1,2):
                b.command(chat, '/follow '+W)
                b.command(chat, '/subscribe')
            b.clock=lambda:1002
            sent=[]
            def send(chat,text,markup):
                if chat == 1: raise OSError('offline')
                sent.append((chat,text,markup))
                return True
            for data in (snap(1000),snap(1003),snap(300),snap(1001,verified=False)):
                b.deliver(data,send)
            stale=snap(); stale['updatedAt']='1970-01-01T00:00:00Z'
            b.deliver(stale,send)
            self.assertEqual(sent,[])
            b.deliver(snap(),send); b.deliver(snap(),send)
            self.assertEqual(len(sent),1)
            self.assertIn('https://solscan.io/tx/',str(sent))
            self.assertEqual(b.db.execute('SELECT count(*) FROM delivered').fetchone()[0],1)
            b.command(2,'/unfollow '+W); b.command(2,'/follow '+W)
            b.deliver(snap(1001,id='1'*64+':18'),send)
            self.assertEqual(len(sent),1)
            b.db.close()
            b=bot.Bot(str(Path(d)/'b.db'),clock=lambda:1004)
            b.deliver(snap(1003),send)
            self.assertEqual(len(sent),1)
            b.db.close()

    def test_transport_bounds_and_cooldown(self):
        import io, json, urllib.error
        class Opener:
            calls=0
            def open(self, req, timeout):
                self.calls+=1
                self.req=req
                raise urllib.error.HTTPError(req.full_url,429,'secret',{},io.BytesIO(json.dumps({'parameters':{'retry_after':99999}}).encode()))
        opener=Opener()
        t=bot.Transport('123:FAKE',opener=opener,clock=lambda:1000)
        self.assertFalse(t.send(1,'hello',bot.buttons()))
        self.assertEqual(t.cooldown,100999)
        self.assertFalse(t.send(1,'again',bot.buttons()))
        self.assertEqual(opener.calls,1)
        self.assertNotIn('parse_mode',json.loads(opener.req.data))
        self.assertIsNone(bot.NoRedirect().redirect_request(None,None,302,'',{},'https://evil.test'))
        class Big:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,n): return b'x'*n
        class Large:
            def open(self,*args,**kwargs): return Big()
        self.assertIsNone(bot.Transport('',opener=Large()).snapshot())

    def test_update_offset_stop_before_failed_ack(self):
        with tempfile.TemporaryDirectory() as d:
            path=str(Path(d)/'b.db')
            b=bot.Bot(path,clock=lambda:1000)
            b.command(1,'/subscribe')
            def fail(*args): raise OSError('no')
            b.updates([{'update_id':7,'message':{'chat':{'id':1,'type':'private'},'text':'/stop'}}],fail)
            self.assertFalse(b.state(1)['active'])
            self.assertEqual(b.offset(),8)
            b.db.close()
            b=bot.Bot(path)
            self.assertEqual(b.offset(),8)
            b.db.close()
            with bot.worker_lock(path):
                with self.assertRaises(RuntimeError):
                    with bot.worker_lock(path): pass

    def test_entrypoint_safe_help_and_required_token(self):
        import subprocess,sys,os
        result=subprocess.run([sys.executable,bot.__file__,'--help'],capture_output=True,text=True)
        self.assertIn('--smoke',result.stdout)
        env=dict(os.environ); env.pop('TRENCHNET_BOT_TOKEN',None)
        result=subprocess.run([sys.executable,bot.__file__],env=env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('TRENCHNET_BOT_TOKEN',result.stderr)

    def test_transport_paces_without_dropping_second_recipient(self):
        import io
        now=[1000.0]
        class Response(io.BytesIO): pass
        class Opener:
            def open(self,*args,**kwargs): return Response(b'{"ok":true}')
        def sleep(delay): now[0]+=delay
        t=bot.Transport('123:FAKE',opener=Opener(),clock=lambda:now[0],sleep=sleep)
        self.assertTrue(t.send(1,'first',bot.buttons()))
        self.assertTrue(t.send(2,'second',bot.buttons()))
        self.assertGreaterEqual(now[0],1001.1)

    def test_malformed_status_fails_closed(self):
        s=snap(); s['status']=None
        self.assertEqual(bot.normalize(s,1002),[])

    def test_consent_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / 'bot.db')
            b = bot.Bot(path, clock=lambda: 1000)
            self.assertIn('limited Pump', b.command(1, '/start'))
            self.assertFalse(b.state(1)['active'])
            b.command(1, '/follow '+W)
            b.command(1, '/subscribe')
            self.assertTrue(b.state(1)['active'])
            b.clock = lambda: 1010
            b.command(1, '/subscribe')
            self.assertEqual(b.state(1)['since'], 1000)
            b.command(1, '/start')
            self.assertTrue(b.state(1)['active'])
            b.command(1, '/stop')
            b.db.close()
            b = bot.Bot(path, clock=lambda: 1020)
            self.assertFalse(b.state(1)['active'])
            self.assertIn(W, b.command(1, '/status'))
            self.assertIsNone(b.command(2, '/subscribe', private=False))
            self.assertIsNone(b.state(2))
            self.assertIn('valid', b.command(1, '/follow '+ 'z'*44))
            self.assertIn('Removed', b.command(1, '/unfollow '+W))
            b.db.close()
