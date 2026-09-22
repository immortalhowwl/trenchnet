"""Isolated opt-in, read-only TRENCHNET Telegram worker (stdlib only)."""
import sqlite3
import time
import json
import os
import re
import fcntl
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from contextlib import contextmanager

SNAPSHOT_URL = 'https://trenchnet.app/api/snapshot'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Transport:
    def __init__(self, token, opener=None, clock=time.time, sleep=time.sleep):
        self.sleep = sleep
        self.token = token
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.clock = clock
        self.cooldown = 0
        self.next_send = 0

    def request(self, url, payload=None, telegram=False):
        if telegram and self.clock() < self.cooldown:
            return None
        try:
            data = None if payload is None else json.dumps(payload).encode()
            req = urllib.request.Request(url,data=data,headers={'Content-Type':'application/json','User-Agent':'TrenchnetBot/1.0'})
            with self.opener.open(req,timeout=30) as response:
                raw = response.read(2_000_001)
                if len(raw)>2_000_000:
                    return None
                obj = json.loads(raw)
                if not isinstance(obj,dict):
                    return None
                if telegram and obj.get('error_code') == 429:
                    self.rate_limit(obj)
                    return None
                return obj
        except urllib.error.HTTPError as exc:
            if telegram and exc.code == 429:
                try:
                    self.rate_limit(json.loads(exc.read(8192)))
                except Exception:
                    self.cooldown = self.clock()+60
            exc.close()
        except Exception:
            pass  # Never log token-bearing URLs or exception bodies.
        return None

    def rate_limit(self, obj):
        delay = obj.get('parameters',{}).get('retry_after',60)
        try:
            delay = max(1,int(delay))
        except (TypeError,ValueError,OverflowError):
            delay = 60
        self.cooldown = self.clock()+delay

    def telegram(self, method, payload):
        if method not in ('sendMessage','getUpdates') or not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+',self.token):
            return None
        return self.request('https://api.telegram.org/bot'+self.token+'/'+method,payload,True)

    def send(self, chat, text, markup):
        if self.clock() < self.cooldown:
            return False
        delay = min(1.1,max(0,self.next_send-self.clock()))
        if delay:
            self.sleep(delay)
        self.next_send = self.clock()+1.1
        result = self.telegram('sendMessage',{'chat_id':chat,'text':text[:4000],
                              'reply_markup':markup,'link_preview_options':{'is_disabled':True}})
        return bool(result and result.get('ok') is True)

    def snapshot(self):
        return self.request(SNAPSHOT_URL)

    def poll(self, offset):
        result = self.telegram('getUpdates',{'offset':offset,'timeout':20,'limit':100,'allowed_updates':['message']})
        return result.get('result',[]) if result and result.get('ok') is True else None


@contextmanager
def worker_lock(path):
    with open(str(Path(path).resolve())+'.lock','a') as handle:
        try:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another worker owns this database') from None
        try:
            yield
        finally:
            fcntl.flock(handle,fcntl.LOCK_UN)


ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
WELCOME = ('TRENCHNET monitors a retained limited Pump trade sample, not all wallet activity. '
           'No profit, ranking or complete-exit claims. Alerts start OFF for new chats. '
           'Use /follow <Solana wallet>, then /subscribe. /stop pauses alerts. '
           '/unfollow <wallet>, /status, /help. https://trenchnet.app')


def base58(value, size):
    if not isinstance(value, str) or not 1 <= len(value) <= 90:
        return False
    n = 0
    for c in value:
        if c not in ALPHABET:
            return False
        n = n * 58 + ALPHABET.index(c)
    return len(value) - len(value.lstrip('1')) + (n.bit_length()+7)//8 == size


from datetime import datetime


def instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo else None
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def normalize(snapshot, now):
    if not isinstance(snapshot, dict) or snapshot.get('version') != 'trenchnet-v1':
        return []
    stamp = instant(snapshot.get('updatedAt'))
    status = snapshot.get('status')
    if stamp is None or not 0 <= now-stamp <= 600 or not isinstance(status,dict) or status.get('collector') != 'ok':
        return []
    rows = snapshot.get('trades')
    if not isinstance(rows, list):
        return []
    result = {}
    for t in rows[:500]:
        if not isinstance(t, dict):
            continue
        ts = instant(t.get('timestamp'))
        sig = t.get('signature')
        eid = t.get('id')
        if (t.get('verified') is not True or t.get('side') not in ('buy','sell')
            or t.get('source') != 'Pump TradeEvent / finalized Solana RPC'
            or ts is None or not 0 <= now-ts <= 600 or ts > stamp
            or not base58(t.get('wallet'),32) or not base58(t.get('mint'),32)
            or not base58(sig,64) or not isinstance(eid,str)
            or not eid.startswith(sig+':') or not eid[len(sig)+1:].isascii()
            or not eid[len(sig)+1:].isdigit() or len(eid)>110):
            continue
        result.setdefault(eid, dict(t, epoch=ts))
    return sorted(result.values(), key=lambda t:(t['epoch'],t['id']))


def buttons(signature=None):
    row = [{'text':'TRENCHNET', 'url':'https://trenchnet.app'}]
    if signature and base58(signature,64):
        row.append({'text':'Solscan transaction','url':'https://solscan.io/tx/'+signature})
    return {'inline_keyboard':[row]}


class Bot:
    def __init__(self, path, clock=time.time):
        self.clock = clock
        self.boot = clock()
        self.db = sqlite3.connect(path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS recipients(chat INTEGER PRIMARY KEY, active INTEGER DEFAULT 0, since REAL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS follows(chat INTEGER, wallet TEXT COLLATE BINARY, since REAL, PRIMARY KEY(chat,wallet));
            CREATE TABLE IF NOT EXISTS delivered(chat INTEGER,event TEXT,PRIMARY KEY(chat,event));
            CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value INTEGER);
        ''')

    def deliver(self, snapshot, send):
        attempted = 0
        for t in normalize(snapshot, self.clock()):
            rows = self.db.execute('''SELECT r.chat,r.since,f.since AS followed FROM recipients r
                JOIN follows f ON r.chat=f.chat WHERE r.active=1 AND f.wallet=?''', (t['wallet'],)).fetchall()
            for r in rows:
                if attempted >= 20:
                    return
                if t['epoch'] <= max(self.boot,r['since'],r['followed']):
                    continue
                if not normalize(snapshot,self.clock()):
                    return
                if self.clock()-t['epoch'] > 600:
                    continue
                if self.db.execute('SELECT 1 FROM delivered WHERE chat=? AND event=?', (r['chat'],t['id'])).fetchone():
                    continue
                attempted += 1
                text = ('Monitored '+t['side'].upper()+' observed\nEvent account: '+t['wallet']+
                        '\nToken: '+t['mint']+'\nObserved at: '+t['timestamp']+'\nRetained Pump sample only; not full activity or profit.')
                try:
                    ok = send(r['chat'],text,buttons(t['signature']))
                except Exception:
                    ok = False
                if ok:
                    with self.db:
                        self.db.execute('INSERT OR IGNORE INTO delivered VALUES(?,?)',(r['chat'],t['id']))

    def offset(self):
        row = self.db.execute("SELECT value FROM state WHERE key='offset'").fetchone()
        return row[0] if row else 0

    def updates(self, updates, send):
        for update in updates[:100]:
            if not isinstance(update,dict) or type(update.get('update_id')) is not int:
                continue
            uid=update['update_id']
            if uid < self.offset():
                continue
            msg=update.get('message',{})
            chat=msg.get('chat',{})
            reply=None
            if chat.get('type') == 'private' and type(chat.get('id')) is int and isinstance(msg.get('text'),str):
                reply=self.command(chat['id'],msg['text'][:4096])
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO state VALUES('offset',?)",(uid+1,))
            if reply:
                try:
                    send(chat['id'],reply,buttons())
                except Exception:
                    pass

    def state(self, chat):
        return self.db.execute('SELECT * FROM recipients WHERE chat=?', (chat,)).fetchone()

    def command(self, chat, text, private=True):
        if not private:
            return None
        parts = text.split()
        cmd = parts[0] if parts else ''
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO recipients(chat) VALUES(?)', (chat,))
            if cmd == '/stop':
                self.db.execute('UPDATE recipients SET active=0 WHERE chat=?', (chat,))
                return 'Alerts OFF. Your followed wallets are retained.'
            if cmd in ('/follow', '/unfollow'):
                if len(parts) != 2 or not base58(parts[1], 32):
                    return 'Enter a valid 32-byte base58 Solana wallet.'
                wallet = parts[1]
                if cmd == '/unfollow':
                    self.db.execute('DELETE FROM follows WHERE chat=? AND wallet=?', (chat,wallet))
                    return 'Removed wallet.'
                count = self.db.execute('SELECT count(*) FROM follows WHERE chat=?', (chat,)).fetchone()[0]
                if count >= 10:
                    return 'Limit: 10 followed wallets. Use /unfollow first.'
                self.db.execute('INSERT OR IGNORE INTO follows VALUES(?,?,?)', (chat,wallet,self.clock()))
                return 'Following '+wallet+'. Use /subscribe to enable alerts.'
            if cmd == '/subscribe':
                self.db.execute('UPDATE recipients SET active=1,since=? WHERE chat=? AND active=0', (self.clock(),chat))
                return 'Alerts ON for new monitored buys and sells only.'
            if cmd == '/status':
                wallets = [r[0] for r in self.db.execute('SELECT wallet FROM follows WHERE chat=? ORDER BY wallet', (chat,))]
                return ('Alerts ON' if self.state(chat)['active'] else 'Alerts OFF')+'\nFollowed wallets:\n'+'\n'.join(wallets)
        return WELCOME


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke',action='store_true',help='Read public snapshot and normalize only; never contacts Telegram')
    args=parser.parse_args()
    if args.smoke:
        snapshot=Transport('').snapshot()
        if snapshot is None:
            parser.exit(1,'Public snapshot unavailable\n')
        print(json.dumps({'source':SNAPSHOT_URL,'updatedAt':snapshot.get('updatedAt'),
                          'retainedTrades':len(snapshot.get('trades',[])),
                          'freshVerifiedTrades':len(normalize(snapshot,time.time())),
                          'telegramContacted':False}))
        return
    token=os.environ.get('TRENCHNET_BOT_TOKEN','')
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+',token):
        parser.exit(2,'Launch blocked: valid TRENCHNET_BOT_TOKEN required.\n')
    os.umask(0o077)
    path=Path(os.environ.get('BOT_DB_PATH',str(Path(__file__).parent/'data'/'telegram-bot.sqlite'))).resolve()
    path.parent.mkdir(parents=True,exist_ok=True)
    with worker_lock(path):
        b=Bot(str(path))
        transport=Transport(token)
        try:
            while True:
                updates=transport.poll(b.offset())
                if not isinstance(updates,list):
                    time.sleep(3)
                    continue  # Do not send alerts if pending stop commands cannot be fetched.
                b.updates(updates,transport.send)
                if len(updates)<100:
                    snapshot=transport.snapshot()
                    if snapshot:
                        b.deliver(snapshot,transport.send)
                time.sleep(2)
        except KeyboardInterrupt:
            pass
        finally:
            b.db.close()


if __name__ == '__main__':
    main()

