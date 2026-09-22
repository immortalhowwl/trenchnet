"""Bounded read-only public collection. Raw upstream receipts live alongside SQLite."""
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import struct
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen

PROGRAM = '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
IDL_URL = 'https://raw.githubusercontent.com/pump-fun/pump-public-docs/main/idl/pump.json'
RPCS = ('https://solana-rpc.publicnode.com', 'https://api.mainnet-beta.solana.com')
SOL = 'So11111111111111111111111111111111111111112'
ZERO = '11111111111111111111111111111111'

def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace('+00:00', 'Z')

def init_db(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path), timeout=10) as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE IF NOT EXISTS markets(address TEXT PRIMARY KEY,fetched_at TEXT,payload TEXT); CREATE TABLE IF NOT EXISTS trades(id TEXT PRIMARY KEY,timestamp TEXT,payload TEXT);')

def fetch(url, directory, payload=None):
    started = utc_now()
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=data, headers={'User-Agent':'TRENCHNET/1.0 public-read-only', 'Content-Type':'application/json'})
    with urlopen(request, timeout=12) as response:
        body = response.read(6_000_001)
        if len(body) > 6_000_000:
            raise ValueError('Upstream response exceeds bound')
        status = response.status
    decoded = json.loads(body)
    digest = hashlib.sha256(body).hexdigest()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    record = dict(url=url, request=payload, startedAt=started, receivedAt=utc_now(), httpStatus=status,
                  sha256=digest, body=body.decode())
    name = hashlib.sha256((url + json.dumps(payload) + digest).encode()).hexdigest()
    (directory / (name + '.json')).write_text(json.dumps(record), encoding='utf-8')
    return decoded

def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None

def collect_markets(directory):
    discovery = fetch('https://api.dexscreener.com/token-boosts/latest/v1', directory)
    addresses = list(dict.fromkeys(x['tokenAddress'] for x in discovery if x.get('chainId') == 'solana'))[:20]
    if not addresses:
        return []
    pairs = fetch('https://api.dexscreener.com/tokens/v1/solana/' + ','.join(addresses), directory)
    best = {}
    for p in pairs:
        mint = p.get('baseToken', {}).get('address')
        if p.get('chainId') != 'solana' or mint not in addresses:
            continue
        liquidity = number(p.get('liquidity', {}).get('usd')) or 0
        if mint in best and liquidity <= (best[mint]['liquidityUsd'] or 0):
            continue
        best[mint] = dict(address=mint, symbol=p['baseToken'].get('symbol', ''), name=p['baseToken'].get('name', ''),
            priceUsd=number(p.get('priceUsd')), marketCap=number(p.get('marketCap')),
            liquidityUsd=number(p.get('liquidity', {}).get('usd')), volume24h=number(p.get('volume', {}).get('h24')),
            change24h=number(p.get('priceChange', {}).get('h24')), pairUrl=p.get('url'),
            imageUrl=p.get('info', {}).get('imageUrl'), createdAt=iso(p['pairCreatedAt']/1000) if p.get('pairCreatedAt') else None,
            source='DexScreener', fetchedAt=utc_now(), discovery='paid-boost-list; not a wallet signal')
    return list(best.values())

def b58(raw):
    n, text = int.from_bytes(raw, 'big'), ''
    alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    while n:
        n, r = divmod(n, 58)
        text = alphabet[r] + text
    return '1' * (len(raw) - len(raw.lstrip(b'\0'))) + text

class Borsh:
    def __init__(self, data, types):
        self.data, self.offset, self.types = data, 0, types

    def take(self, size):
        end = self.offset + size
        if end > len(self.data): raise ValueError('Truncated Borsh event')
        out, self.offset = self.data[self.offset:end], end
        return out

    def read(self, kind):
        if kind == 'pubkey': return b58(self.take(32))
        if kind in ('u64', 'i64', 'u32', 'u16', 'u8'):
            size = {'u64':8,'i64':8,'u32':4,'u16':2,'u8':1}[kind]
            return int.from_bytes(self.take(size), 'little', signed=kind=='i64')
        if kind == 'bool':
            value = self.take(1)[0]
            if value > 1: raise ValueError('Invalid bool')
            return bool(value)
        if kind == 'string':
            length = self.read('u32')
            if length > 256: raise ValueError('String bound')
            return self.take(length).decode()
        if isinstance(kind, dict) and 'vec' in kind:
            count = self.read('u32')
            if count > 128: raise ValueError('Vector bound')
            return [self.read(kind['vec']) for _ in range(count)]
        if isinstance(kind, dict) and 'defined' in kind:
            return self.record(kind['defined']['name'])
        raise ValueError('Unsupported IDL type')

    def record(self, name):
        return {f['name']:self.read(f['type']) for f in self.types[name]['fields']}

def decode_transaction(tx, signature, idl):
    if not tx or not tx.get('meta') or tx['meta'].get('err') is not None: return []
    if signature not in tx.get('transaction', {}).get('signatures', []): return []
    if tx.get('blockTime') is None or idl.get('address') != PROGRAM: return []
    # Fail closed: caught CPI failures can roll back emitted events even when meta.err is null.
    if any(re.match(r'Program \w+ failed:', line) for line in tx['meta'].get('logMessages') or []): return []
    types = {x['name']:x['type'] for x in idl['types']}
    discriminator = bytes(next(x['discriminator'] for x in idl['events'] if x['name']=='TradeEvent'))
    meta, stack, events = tx['meta'], [], []
    for index, line in enumerate(meta.get('logMessages') or []):
        invoke = re.fullmatch(r'Program (\w+) invoke \[(\d+)\]', line)
        done = re.match(r'Program (\w+) (success|failed:)', line)
        if invoke:
            depth = int(invoke[2])
            if depth != len(stack) + 1: return []
            stack.append(invoke[1])
        elif done:
            if stack and stack[-1] == done[1]: stack.pop()
            else: return []
        elif line.startswith('Program data: ') and stack and stack[-1] == PROGRAM:
            try:
                data = base64.b64decode(line[14:], validate=True)
                if data[:8] != discriminator: continue
                reader = Borsh(data[8:], types)
                event = reader.record('TradeEvent')
                if reader.offset != len(data)-8: continue
                if abs(event['timestamp'] - tx['blockTime']) > 300: continue
                events.append((index,event))
            except (ValueError, KeyError, UnicodeError):
                continue
    if stack: return []  # Truncated/unbalanced invocation logs cannot establish committed events.
    # Verify aggregate owner/mint delta. Multiple fills retain distinct log identities.
    totals, decimals = {}, {}
    for key, sign in [('preTokenBalances',-1), ('postTokenBalances',1)]:
        for item in meta.get(key) or []:
            owner = item.get('owner')
            if not owner: continue
            pair = (owner,item['mint'])
            totals[pair] = totals.get(pair,0) + sign * int(item['uiTokenAmount']['amount'])
            decimals[pair] = item['uiTokenAmount']['decimals']
    expected = {}
    for _,e in events:
        pair = (e['user'],e['mint'])
        expected[pair] = expected.get(pair,0) + (1 if e['is_buy'] else -1)*e['token_amount']
    output = []
    signers = [k['pubkey'] for k in tx['transaction']['message'].get('accountKeys',[]) if isinstance(k,dict) and k.get('signer')]
    for index,e in events:
        pair = (e['user'],e['mint'])
        if pair not in totals or totals[pair] != expected[pair] or e['token_amount'] <= 0: continue
        # Current schema explicitly names quote mint. Unknown quotes are not SOL.
        quote = e.get('quote_mint')
        sol_amount = e['sol_amount']/1e9 if quote in (ZERO,SOL) else None
        output.append(dict(id=signature+':'+str(index),signature=signature,wallet=e['user'],mint=e['mint'],
            side='buy' if e['is_buy'] else 'sell',tokenAmount=e['token_amount']/10**decimals[pair],
            solAmount=sol_amount,timestamp=iso(e['timestamp']),source='Pump TradeEvent / finalized Solana RPC',
            explorerUrl='https://solscan.io/tx/'+signature,verified=True,tokenAmountRaw=str(e['token_amount']),
            solAmountRaw=str(e['sol_amount']),quoteMint=quote,quoteAmountRaw=str(e.get('quote_amount',0)),
            signers=signers,eventUserIsSigner=e['user'] in signers,mayhemMode=e.get('mayhem_mode',False),
            actorAttribution='Observed event account; not a verified human or profitable trader'))
    return output

def rpc(url, method, params, directory):
    data = fetch(url, directory, {'jsonrpc':'2.0','id':1,'method':method,'params':params})
    if data.get('error'): raise RuntimeError(str(data['error']))
    return data.get('result')

def collect_trades(directory):
    idl = fetch(IDL_URL, directory)
    if idl.get('address') != PROGRAM: raise ValueError('Official IDL program mismatch')
    signatures, endpoint, errors = None, None, []
    discovery_address = PROGRAM
    try:
        coins = fetch('https://frontend-api-v3.pump.fun/coins?offset=0&limit=3&sort=last_trade_timestamp&order=DESC&includeNsfw=false', directory)
        discovery_address = next((c['bonding_curve'] for c in coins if c.get('bonding_curve') and not c.get('complete')), PROGRAM)
    except Exception:
        pass  # Optional metadata source; program-address fallback remains bounded.
    for candidate in RPCS:
        try:
            signatures = rpc(candidate,'getSignaturesForAddress',[discovery_address,{'limit':20,'commitment':'finalized'}],directory)
            endpoint = candidate
            break
        except Exception as exc:
            errors.append(str(exc))
    if endpoint is None: raise RuntimeError('Public RPC discovery failed: '+'; '.join(errors))
    class Observations(list):
        pass
    output = Observations()
    output.errors = []
    for item in [x for x in (signatures or []) if x.get('err') is None][:10]:
        time.sleep(.35)
        try:
            tx = rpc(endpoint,'getTransaction',[item['signature'],{'encoding':'jsonParsed','maxSupportedTransactionVersion':0,'commitment':'finalized'}],directory)
            if tx is None:
                output.errors.append('getTransaction: result null')
            else:
                output.extend(decode_transaction(tx,item['signature'],idl))
        except Exception as exc:
            output.errors.append('getTransaction: '+str(exc)[:160])
            # Stop on rate limits rather than hammering the provider.
            if getattr(exc, 'code', None) == 429: break
    return output

def collect_once(db_path):
    init_db(db_path)
    directory = Path(db_path).parent / 'receipts'
    errors, markets, trades = [], [], []
    for label, fn in [('markets', collect_markets), ('trades', collect_trades)]:
        try:
            records = fn(directory)
            errors.extend(getattr(records, 'errors', []))
            if label == 'markets': markets = records
            else: trades = records
            if not records: errors.append(label + ': no verified observations in bounded sample')
        except Exception as exc:
            errors.append(label + ': ' + str(exc)[:240])
    status = 'ok' if not errors else ('partial' if markets or trades else 'error')
    summary = dict(updatedAt=utc_now(), collector=status, message='; '.join(errors) if errors else 'Public market and finalized Pump observations collected.', markets=len(markets), trades=len(trades))
    with sqlite3.connect(str(db_path), timeout=10) as c:
        c.executemany('INSERT OR REPLACE INTO markets VALUES(?,?,?)', [(x['address'],x['fetchedAt'],json.dumps(x)) for x in markets])
        c.executemany('INSERT OR IGNORE INTO trades VALUES(?,?,?)', [(x['id'],x['timestamp'],json.dumps(x)) for x in trades])
        c.execute('INSERT OR REPLACE INTO state VALUES(?,?)', ('collector',json.dumps(summary)))
        c.execute('DELETE FROM markets WHERE address NOT IN (SELECT address FROM markets ORDER BY fetched_at DESC LIMIT 100)')
        c.execute('DELETE FROM trades WHERE id NOT IN (SELECT id FROM trades ORDER BY timestamp DESC LIMIT 2000)')
    # Keep disk use bounded, retaining the newest raw requests across collection cycles.
    if directory.exists():
        for old in sorted(directory.glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True)[1200:]:
            old.unlink()
    return summary
