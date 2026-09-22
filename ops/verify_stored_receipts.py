"""Replay saved raw RPC receipts with the current conservative decoder (read only)."""
from pathlib import Path
import json
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collector

root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]/'data'
raw={}
idl=None
for path in sorted((root/'receipts').rglob('*.json'), key=lambda p:p.stat().st_mtime):
    record=json.loads(path.read_text())
    if 'body' not in record: continue
    body=json.loads(record['body'])
    if record['url']==collector.IDL_URL: idl=body
    tx=body.get('result') if isinstance(body,dict) else None
    if isinstance(tx,dict) and tx.get('transaction'):
        for sig in tx['transaction'].get('signatures',[]): raw[sig]=tx
with sqlite3.connect('file:'+str(root/'trenchnet.sqlite')+'?mode=ro',uri=True) as conn:
    rows=[json.loads(x[0]) for x in conn.execute('select payload from trades')]
invalid=[]
for trade in rows:
    decoded=collector.decode_transaction(raw.get(trade['signature']),trade['signature'],idl)
    if not any(x['id']==trade['id'] and x['tokenAmountRaw']==trade['tokenAmountRaw'] for x in decoded):
        invalid.append(trade['id'])
print(json.dumps({'checked':len(rows),'invalid':invalid,'decoder':'rollback-safe; current IDL'},indent=2))
raise SystemExit(1 if invalid else 0)
