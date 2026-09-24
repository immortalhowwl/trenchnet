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
        if method not in ('sendMessage','getUpdates','answerCallbackQuery') or not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+',self.token):
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

    def answer(self, callback_id):
        result = self.telegram('answerCallbackQuery', {'callback_query_id':callback_id})
        return bool(result and result.get('ok') is True)

    def snapshot(self):
        return self.request(SNAPSHOT_URL)

    def poll(self, offset):
        result = self.telegram('getUpdates',{'offset':offset,'timeout':20,'limit':100,'allowed_updates':['message','callback_query']})
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
           'Tap Add wallet, send a trader wallet address, then tap Enable alerts. '
           'Adding a wallet does not extend collector coverage. No wallet connection required. '
           'Pause alerts retains your wallets. Recent trades is read-only. '
           'Commands: /follow <wallet>, /unfollow <wallet>, /wallets, /subscribe, /stop, '
           '/feed, /status, /cancel, /help. https://trenchnet.app')


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
    return {'inline_keyboard':[row,
        [{'text':'Add wallet','callback_data':'add'}, {'text':'My wallets','callback_data':'wallets'}],
        [{'text':'Remove wallet','callback_data':'remove'}],
        [{'text':'Enable alerts','callback_data':'enable'}, {'text':'Pause alerts','callback_data':'pause'}],
        [{'text':'Recent trades','callback_data':'feed'}, {'text':'Status','callback_data':'status'}],
        [{'text':'Help','callback_data':'help'}, {'text':'Cancel','callback_data':'cancel'}]]}


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
            CREATE TABLE IF NOT EXISTS inputs(chat INTEGER PRIMARY KEY, action TEXT NOT NULL);
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

    def updates(self, updates, send, snapshot=None, answer=None):
        for update in updates[:100]:
            if not isinstance(update,dict) or type(update.get('update_id')) is not int:
                continue
            uid=update['update_id']
            if uid < self.offset():
                continue
            msg = update.get('message')
            msg = msg if isinstance(msg, dict) else {}
            cb = update.get('callback_query')
            text = msg.get('text')
            if isinstance(cb, dict):
                msg = cb.get('message')
                msg = msg if isinstance(msg, dict) else {}
                owner = cb.get('from')
                owner = owner if isinstance(owner, dict) else {}
                target = msg.get('chat')
                target = target if isinstance(target, dict) else {}
                actions = {'enable':'/subscribe', 'pause':'/stop', 'help':'/help',
                           'status':'/status', 'wallets':'/wallets', 'add':'/follow',
                           'remove':'/unfollow', 'cancel':'/cancel', 'feed':'/feed'}
                data = cb.get('data')
                text = actions.get(data) if isinstance(data, str) else None
                if (type(owner.get('id')) is not int or owner.get('id') != target.get('id')):
                    text = None
            chat = msg.get('chat')
            chat = chat if isinstance(chat, dict) else {}
            reply = None
            cmd = ''
            if chat.get('type') == 'private' and type(chat.get('id')) is int and isinstance(text, str):
                reply = self.command(chat['id'], text[:4096])
                cmd = text.split()[0] if text.split() else ''
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO state VALUES('offset',?)",(uid+1,))
            # Persist pause/preferences and offset before any acknowledgement I/O.
            if isinstance(cb, dict) and answer and isinstance(cb.get('id'), str):
                try:
                    answer(cb['id'])
                except Exception:
                    pass
            if reply:
                if cmd in ('/status', '/feed'):
                    view = self.source_view(snapshot, feed=cmd == '/feed')
                    reply = view if cmd == '/feed' else reply+'\n\n'+view
                try:
                    send(chat['id'],reply,buttons())
                except Exception:
                    pass

    def state(self, chat):
        return self.db.execute('SELECT * FROM recipients WHERE chat=?', (chat,)).fetchone()

    def source_view(self, snapshot, feed=False):
        """Read-only view; the same conservative validation as alerts, no replay state."""
        try:
            data = snapshot() if snapshot else None
        except Exception:
            data = None
        if not isinstance(data, dict) or data.get('version') != 'trenchnet-v1':
            return 'Source unavailable. Fresh observations cannot be confirmed.'
        stamp = instant(data.get('updatedAt'))
        status = data.get('status')
        collector = status.get('collector') if isinstance(status, dict) else None
        collector = collector if collector in ('ok', 'partial', 'error', 'starting') else 'unknown'
        timestamp = str(data.get('updatedAt'))[:80] if stamp is not None else 'unknown'
        fresh = stamp is not None and 0 <= self.clock()-stamp <= 600
        text = ('Source updated at: '+timestamp+'\nCollector: '+collector+
                ('\nFreshness: within 10 minutes.' if fresh else '\nFreshness: stale or invalid timestamp.')+
                '\nRetained limited Pump sample only; not full wallet activity or profit.')
        if not fresh or collector != 'ok':
            return text+'\nFeed and alerts suppressed until source is fresh and collector is ok.'
        if not feed:
            return text
        trades = list(reversed(normalize(data, self.clock())))[:5]
        if not trades:
            return text+'\nNo eligible recent observed trades in this sample; not evidence of no on-chain activity.'
        text += '\n\nRecent observed trades (all sampled wallets, up to 5):'
        for trade in trades:
            text += ('\n\n'+trade['side'].upper()+' observed at: '+trade['timestamp'][:80]+
                     '\nWallet: '+trade['wallet']+'\nToken: '+trade['mint']+
                     '\nhttps://solscan.io/tx/'+trade['signature'])
        return text

    def pending(self, chat):
        row = self.db.execute('SELECT action FROM inputs WHERE chat=?', (chat,)).fetchone()
        return row[0] if row else None

    def command(self, chat, text, private=True):
        if not private:
            return None
        parts = text.split()
        cmd = parts[0] if parts else ''
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO recipients(chat) VALUES(?)', (chat,))
            if not cmd.startswith('/') and self.pending(chat):
                cmd = self.pending(chat)
                parts = [cmd] + parts
            elif cmd.startswith('/'):
                self.db.execute('DELETE FROM inputs WHERE chat=?', (chat,))
            if cmd == '/cancel':
                return 'Cancelled. Alert settings unchanged.'
            if cmd == '/stop':
                self.db.execute('UPDATE recipients SET active=0 WHERE chat=?', (chat,))
                return 'Alerts OFF. Your followed wallets are retained.'
            if cmd in ('/follow', '/unfollow'):
                if len(parts) == 1:
                    self.db.execute('INSERT OR REPLACE INTO inputs VALUES(?,?)', (chat,cmd))
                    verb = 'follow' if cmd == '/follow' else 'remove'
                    return 'Send the Solana wallet address to '+verb+'. Use /cancel to cancel.'
                if len(parts) != 2 or not base58(parts[1], 32):
                    return 'Enter a valid 32-byte base58 Solana wallet.'
                wallet = parts[1]
                self.db.execute('DELETE FROM inputs WHERE chat=?', (chat,))
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
            if cmd in ('/status', '/wallets'):
                wallets = [r[0] for r in self.db.execute('SELECT wallet FROM follows WHERE chat=? ORDER BY wallet', (chat,))]
                return ('Alerts ON' if self.state(chat)['active'] else 'Alerts OFF')+'\nFollowed wallets:\n'+('\n'.join(wallets) if wallets else 'None yet. Tap Add wallet.')
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
                b.updates(updates,transport.send,snapshot=transport.snapshot,answer=transport.answer)
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

