import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import collector
import analytics

class CollectorTests(unittest.TestCase):
    def test_verified_event_requires_program_stack_and_matching_owner_delta(self):
        import base64, struct
        fields = [{'name': n, 'type': t} for n,t in [('mint','pubkey'),('sol_amount','u64'),('token_amount','u64'),('is_buy','bool'),('user','pubkey'),('timestamp','i64'),('quote_mint','pubkey'),('quote_amount','u64')]]
        idl = {'address':collector.PROGRAM, 'types':[{'name':'TradeEvent','type':{'fields':fields}}], 'events':[{'name':'TradeEvent','discriminator':[189,219,127,211,78,230,97,238]}]}
        raw = bytes([189,219,127,211,78,230,97,238]) + bytes(32) + struct.pack('<QQB',10**9,123,1) + bytes(32) + struct.pack('<q',1700000000) + bytes(32) + struct.pack('<Q',0)
        log = 'Program data: ' + base64.b64encode(raw).decode()
        tx = {'blockTime':1700000000,'transaction':{'signatures':['sig'],'message':{'accountKeys':[]}},'meta':{'err':None,'logMessages':[f'Program {collector.PROGRAM} invoke [1]',log,f'Program {collector.PROGRAM} success'],'preTokenBalances':[],'postTokenBalances':[{'owner':collector.ZERO,'mint':collector.ZERO,'uiTokenAmount':{'amount':'123','decimals':6}}]}}
        trades = collector.decode_transaction(tx, 'sig', idl)
        self.assertEqual(len(trades),1)
        self.assertTrue(trades[0]['verified'])
        self.assertEqual(trades[0]['solAmount'],1)
        self.assertEqual(trades[0]['timestamp'],'2023-11-14T22:13:20Z')
        tx['meta']['logMessages'] = [log]
        self.assertEqual(collector.decode_transaction(tx,'sig',idl),[])
        tx['meta']['logMessages'] = [f'Program {collector.PROGRAM} invoke [1]',log]
        tx['meta']['postTokenBalances'][0]['uiTokenAmount']['amount'] = '124'
        self.assertEqual(collector.decode_transaction(tx,'sig',idl),[])
        tx['meta']['err'] = {'error':'failed'}
        self.assertEqual(collector.decode_transaction(tx,'sig',idl),[])

    def test_uses_public_bonding_curve_for_signature_discovery(self):
        idl = {'address':collector.PROGRAM}
        def fake_fetch(url, directory, payload=None):
            return idl if url == collector.IDL_URL else [{'bonding_curve':'curve'}]
        with patch.object(collector,'fetch',side_effect=fake_fetch), patch.object(collector,'rpc',return_value=[]) as rpc:
            collector.collect_trades('unused')
        self.assertEqual(rpc.call_args.args[2][0],'curve')

    def test_rpc_gaps_report_partial_instead_of_success(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / 'test.sqlite'
            class Partial(list):
                errors = ['getTransaction: result null']
            with patch.object(collector, 'collect_markets', return_value=[]), patch.object(collector, 'collect_trades', return_value=Partial()):
                result = collector.collect_once(db)
            self.assertIn('result null', result['message'])

    def test_market_collection_survives_rpc_failure_and_retains_previous(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / 'test.sqlite'
            market = dict(address='mint', symbol='TEST', name='Fixture', priceUsd=1,
                marketCap=3, liquidityUsd=2, volume24h=4, change24h=0,
                pairUrl='https://dexscreener.com/solana/test', imageUrl=None,
                createdAt=None, source='DexScreener', fetchedAt=collector.utc_now())
            with patch.object(collector, 'collect_markets', return_value=[market]), patch.object(collector, 'collect_trades', side_effect=RuntimeError('RPC unavailable')):
                collector.collect_once(db)
            s = analytics.snapshot(db)
            self.assertEqual(s['status']['collector'], 'partial')
            self.assertEqual(s['markets'], [market])
            with patch.object(collector, 'collect_markets', side_effect=RuntimeError('offline')), patch.object(collector, 'collect_trades', side_effect=RuntimeError('offline')):
                collector.collect_once(db)
            self.assertEqual(analytics.snapshot(db)['markets'], [market])
