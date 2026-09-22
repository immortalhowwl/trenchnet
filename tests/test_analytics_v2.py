import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import analytics
import collector


class AnalyticsV2Tests(unittest.TestCase):
    def snapshot(self, trades):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'sample.sqlite'
            collector.init_db(db)
            with sqlite3.connect(db) as conn:
                conn.executemany('INSERT INTO trades VALUES(?,?,?)', [
                    (str(i), t['timestamp'], json.dumps(t)) for i, t in enumerate(trades)])
            before = db.read_bytes()
            result = analytics.snapshot(db)
            self.assertEqual(result, analytics.snapshot(db))
            self.assertEqual(before, db.read_bytes())
            return result

    def trade(self, id, wallet='a', mint='x', side='buy', stamp='2026-09-22T00:00:00Z', **extra):
        return dict(id=id, wallet=wallet, mint=mint, side=side, timestamp=stamp,
                    **({'verified': True, 'solAmount': 2} | extra))

    def test_repeated_cobuy_requires_distinct_verified_mints(self):
        trades = [self.trade('ax'), self.trade('bx', wallet='b'),
                  self.trade('ax2'), self.trade('bx2', wallet='b'),
                  self.trade('ay', mint='y'), self.trade('by', wallet='b', mint='y'),
                  self.trade('cy', wallet='c', mint='y', verified=False)]
        result = self.snapshot(trades)
        relations = result['graph']['relationships']
        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]['wallets'], ['a', 'b'])
        self.assertEqual(relations[0]['sharedTokens'], ['x', 'y'])
        self.assertEqual(relations[0]['sharedTokenCount'], 2)
        self.assertEqual(set(relations[0]['evidence']), {'ax', 'bx', 'ay', 'by'})
        self.assertEqual(self.snapshot(trades[:4])['graph']['relationships'], [])
        many = [self.trade(f'{w}-{mint}', wallet=f'w{w:03}', mint=mint)
                for w in range(70) for mint in ('x', 'y')]
        capped = self.snapshot(many)['graph']
        self.assertEqual(len(capped['relationships']), 30)
        self.assertEqual(capped['relationshipScope']['walletLimit'], 60)
        self.assertEqual(capped['relationshipScope']['walletsConsidered'], 60)
        self.assertTrue(all(w < 'w060' for r in capped['relationships'] for w in r['wallets']))

    def test_outcome_only_strictly_later_same_mint_one_hour(self):
        trades = [self.trade('early', stamp='2026-09-21T23:59:00Z'),
                  self.trade('trigger', side='sell'), self.trade('equal'),
                  self.trade('equal-offset', stamp='2026-09-22T01:00:00+01:00'),
                  self.trade('later', wallet='b', stamp='2026-09-22T00:01:00Z'),
                  self.trade('boundary', side='sell', stamp='2026-09-22T01:00:00Z'),
                  self.trade('late', stamp='2026-09-22T01:00:01Z'),
                  self.trade('other', mint='y', stamp='2026-09-22T00:01:00Z'),
                  self.trade('bad', verified=False, stamp='2026-09-22T00:01:00Z')]
        result = self.snapshot(trades)
        decision = next(d for d in result['decisions'] if d['id'] == 'SELL_OBSERVED:trigger')
        self.assertEqual(decision['evidence'], ['trigger'])
        outcome = decision['outcome']
        self.assertEqual(outcome['status'], 'observed')
        self.assertEqual(outcome['evidence'], ['later', 'boundary'])
        self.assertEqual((outcome['buys'], outcome['sells'], outcome['wallets']), (1, 1, 2))
        self.assertIn('retained sample', outcome['summary'])
        self.assertNotIn('pnl', outcome)
        pending = next(d for d in result['decisions'] if d['id'] == 'SELL_OBSERVED:boundary')['outcome']
        self.assertEqual(pending['evidence'], ['late'])
        lone = self.snapshot([self.trade('only')])['decisions'][0]['outcome']
        self.assertEqual(lone['status'], 'pending')
        self.assertEqual(lone['evidence'], [])
        many = [self.trade('start')] + [self.trade(str(i), stamp=f'2026-09-22T00:01:{i:02}Z') for i in range(15)]
        first = next(d for d in self.snapshot(many)['decisions'] if d['id'] == 'FIRST_SEEN:start')
        self.assertEqual(first['outcome']['buys'], 15)
        self.assertEqual(len(first['outcome']['evidence']), 10)

    def test_missing_database_exposes_empty_v2_graph_without_creating_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing.sqlite'
            result = analytics.snapshot(path)
            self.assertFalse(path.exists())
        self.assertEqual(result['graph']['relationships'], [])
        self.assertEqual(result['analysis']['version'], 'v2')

    def test_rules_metadata_and_retained_profile_behavior(self):
        result = self.snapshot([
            self.trade('1'), self.trade('1'),
            self.trade('2', side='sell', stamp='2026-09-22T00:01:00Z', solAmount=3),
            self.trade('bad', wallet='unverified', verified=False),
        ])
        self.assertEqual(result['analysis'], {'engine': 'rules', 'version': 'v2', 'paidModels': False})
        self.assertNotIn('models', result['status'])
        self.assertEqual(len(result['traders']), 1)
        profile = result['traders'][0]
        self.assertEqual((profile['buys'], profile['sells'], profile['tokens']), (1, 1, 1))
        self.assertEqual(profile['firstSeen'], '2026-09-22T00:00:00Z')
        self.assertEqual(profile['lastSeen'], '2026-09-22T00:01:00Z')
        self.assertEqual(profile['observedSolBought'], 2)
        self.assertEqual(profile['observedSolSold'], 3)
        self.assertIn('retained sample', profile['summary'])
        self.assertIsNone(profile['pnl'])
        self.assertFalse(profile['historyComplete'])
        self.assertEqual(len(result['trades']), 2)
