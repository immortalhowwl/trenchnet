"""Read-only analytics: bounded observations, never performance claims."""
import json
import sqlite3
from pathlib import Path

COVERAGE = ('Bounded finalized Pump bonding-curve trade sample, not full wallet history. '
            'DexScreener discovery may include paid boosts; not smart money. '
            'No holdings, realized PnL, complete exits or human coordination inferred.')

def snapshot(db_path):
    result = dict(version='trenchnet-v1', updatedAt=None, status=dict(
        collector='starting', message='Waiting for public observations.',
        models=dict(astra='not_connected', jev='not_connected'), coverage=COVERAGE),
        markets=[], trades=[], traders=[], graph=dict(nodes=[], edges=[]), decisions=[])
    if not Path(db_path).exists():
        return result
    with sqlite3.connect(str(db_path), timeout=10) as conn:
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
    profiles, nodes, edges, first_buys, seen_tokens = {}, {}, {}, {}, set()
    def decision(kind, trade, evidence, text):
        result['decisions'].append(dict(id=kind+':'+trade['id'], timestamp=trade['timestamp'],
            mint=trade['mint'],kind=kind,summary=text,evidence=evidence,engine='rules',rulesVersion='v1'))
    for t in sorted(result['trades'], key=lambda t:(t['timestamp'],t['id'])):
        if not t.get('verified'): continue
        w, mint, stamp, side = t['wallet'],t['mint'],t['timestamp'],t['side']
        if w not in profiles:
            profiles[w] = dict(address=w,buys=0,sells=0,tokens=set(),lastSeen=stamp,
                summary='Observed event account, not a profitability ranking. Identity and automation unknown.',historyComplete=False,pnl=None)
        p = profiles[w]
        p[side+'s'] += 1
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
    for p in profiles.values(): p['tokens'] = len(p['tokens'])
    result['traders'] = sorted(profiles.values(),key=lambda p:(p['lastSeen'],p['address']),reverse=True)
    result['graph'] = dict(nodes=list(nodes.values()),edges=list(edges.values()))
    result['decisions'].reverse()
    return result
