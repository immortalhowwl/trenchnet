"""Read-only analytics: bounded observations, never performance claims."""
import json
import sqlite3
import math
from pathlib import Path
from datetime import datetime, timezone
from bisect import bisect_right

COVERAGE = ('Bounded finalized Pump bonding-curve trade sample, not full wallet history. '
            'DexScreener discovery may include paid boosts; not smart money. '
            'No holdings, realized PnL, complete exits or human coordination inferred.')

def snapshot(db_path):
    result = dict(version='trenchnet-v1', updatedAt=None, status=dict(
        collector='starting', message='Waiting for public observations.',
        coverage=COVERAGE),
        analysis=dict(engine='rules',version='v2',paidModels=False),
        markets=[], trades=[], traders=[], graph=dict(nodes=[], edges=[], relationships=[],
            relationshipScope=dict(walletLimit=60,walletsConsidered=0,
                ranking='retained verified buy count descending, address ascending',relationshipLimit=30)), decisions=[])
    if not Path(db_path).exists():
        return result
    with sqlite3.connect(Path(db_path).resolve().as_uri()+'?mode=ro', uri=True, timeout=10) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'state' not in tables:
            return result
        state = conn.execute("SELECT value FROM state WHERE key='collector'").fetchone()
        if state:
            info = json.loads(state[0])
            result['updatedAt'] = info.get('updatedAt')
            result['status'].update({k: info[k] for k in ('collector', 'message')})
        result['markets'] = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM markets ORDER BY fetched_at DESC LIMIT 100')]
        result['trades'] = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM trades ORDER BY timestamp DESC,id LIMIT 500')]
    unique = {}
    for t in sorted(result['trades'], key=lambda t:(t['timestamp'],t['id'],json.dumps(t,sort_keys=True))):
        if t.get('verified') is True and t.get('side') in ('buy','sell'):
            unique.setdefault(t['id'],t)
    result['trades'] = sorted(unique.values(),key=lambda t:(t['timestamp'],t['id']),reverse=True)
    profiles, nodes, edges, first_buys, seen_tokens = {}, {}, {}, {}, set()
    def decision(kind, trade, evidence, text):
        result['decisions'].append(dict(id=kind+':'+trade['id'], timestamp=trade['timestamp'],
            mint=trade['mint'],kind=kind,summary=text,evidence=evidence,engine='rules',rulesVersion='v2'))
    for t in sorted(result['trades'], key=lambda t:(t['timestamp'],t['id'])):
        if not t.get('verified'): continue
        w, mint, stamp, side = t['wallet'],t['mint'],t['timestamp'],t['side']
        if w not in profiles:
            profiles[w] = dict(address=w,buys=0,sells=0,tokens=set(),firstSeen=stamp,lastSeen=stamp,
                observedSolBought=0,observedSolSold=0,
                summary='Observed event account in retained sample only; not a profitability ranking. Identity and automation unknown.',historyComplete=False,pnl=None)
        p = profiles[w]
        p[side+'s'] += 1
        amount = t.get('solAmount')
        if isinstance(amount,(int,float)) and not isinstance(amount,bool) and math.isfinite(amount) and amount >= 0:
            p['observedSolBought' if side == 'buy' else 'observedSolSold'] += amount
        p['tokens'].add(mint)
        p['lastSeen'] = stamp
        wallet_id, token_id = 'wallet:'+w, 'token:'+mint
        nodes[wallet_id] = dict(id=wallet_id,type='wallet',label=w[:6]+'…'+w[-4:])
        nodes[token_id] = dict(id=token_id,type='token',label=mint[:6]+'…'+mint[-4:])
        pair = (w,mint)
        if pair not in edges:
            edges[pair] = dict(source=wallet_id,target=token_id,buys=0,sells=0,firstSeen=stamp,lastSeen=stamp)
        edges[pair][side+'s'] += 1
        edges[pair]['lastSeen'] = stamp
        if mint not in seen_tokens:
            seen_tokens.add(mint)
            decision('FIRST_SEEN',t,[t['id']],'First verified trade in retained observation window; not token creation.')
        if side == 'sell':
            decision('SELL_OBSERVED',t,[t['id']],'Verified sell observed. Not proof of a complete exit or realized profit.')
        else:
            prior = first_buys.setdefault(mint,{})
            if w not in prior:
                if prior:
                    anchor = next(iter(prior.values()))
                    decision('CO_BUY',t,[anchor,t['id']],'Different event accounts bought this token in the retained sample. Not proof of coordination or distinct humans.')
                prior[w] = t['id']
    for p in profiles.values():
        p['tokens'] = len(p['tokens'])
        p['summary'] = (f"In the retained sample: {p['buys']} buys and {p['sells']} sells across {p['tokens']} tokens. "
                        'SOL totals cover observed trades only, not profit or full wallet history.')
    result['traders'] = sorted(profiles.values(),key=lambda p:(p['lastSeen'],p['address']),reverse=True)
    # Top 60 by retained verified buy count, address tie-break. Inverted mint
    # index pairs at most 60 wallets, not the unbounded wallet population.
    # O(trades * 60) pair work; each mint contributes only once per pair.
    eligible = set(p['address'] for p in sorted(profiles.values(),
        key=lambda p:(-p['buys'],p['address']))[:60] if p['buys'])
    pairs = {}
    for mint, buyers in sorted(first_buys.items()):
        wallets = sorted(eligible.intersection(buyers))
        for i, a in enumerate(wallets):
            for b in wallets[i+1:]:
                r = pairs.setdefault((a,b),dict(wallets=[a,b],sharedTokens=[],evidence=[]))
                r['sharedTokens'].append(mint)
                r['evidence'].extend([buyers[a],buyers[b]])
    relationships = []
    for r in pairs.values():
        r['sharedTokenCount'] = len(r['sharedTokens'])
        if r['sharedTokenCount'] >= 2:
            r['summary'] = 'Repeated co-buy observations in retained sample; not proof of coordination.'
            relationships.append(r)
    relationships.sort(key=lambda r:(-r['sharedTokenCount'],r['wallets']))
    result['graph'] = dict(nodes=list(nodes.values()),edges=list(edges.values()),
        relationships=relationships[:30], relationshipScope=dict(walletLimit=60,
        walletsConsidered=len(eligible), ranking='retained verified buy count descending, address ascending',
        relationshipLimit=30))
    # Parse real instants: lexical ordering cannot distinguish timezone offsets.
    def instant(stamp):
        value = datetime.fromisoformat(stamp.replace('Z','+00:00'))
        return value.replace(tzinfo=timezone.utc).timestamp() if value.tzinfo is None else value.timestamp()

    by_mint = {}
    for t in result['trades']:
        by_mint.setdefault(t['mint'], []).append((instant(t['timestamp']), t['id'], t))
    for rows in by_mint.values():
        rows.sort(key=lambda row:(row[0],row[1]))
    for d in result['decisions']:
        rows = by_mint[d['mint']]
        stamps = [row[0] for row in rows]
        start = instant(d['timestamp'])
        later = [row[2] for row in rows[bisect_right(stamps,start):bisect_right(stamps,start+3600)]]
        buys = sum(t['side'] == 'buy' for t in later)
        sells = len(later)-buys
        wallets = len({t['wallet'] for t in later})
        d['outcome'] = dict(status='observed' if later else 'pending',buys=buys,
            sells=sells,wallets=wallets,evidence=[t['id'] for t in later[:10]],
            summary=(f'In retained sample: {buys} buys, {sells} sells, {wallets} event accounts strictly later within one hour. '
                     'Observed activity only; not profit or prediction evaluation.' if later else
                     'No strictly later verified trades within one hour in retained sample; observation pending, not proof of inactivity.'))
    result['decisions'].reverse()
    return result
