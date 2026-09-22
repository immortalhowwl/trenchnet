import tempfile
import unittest
from pathlib import Path
import analytics

class AnalyticsTests(unittest.TestCase):
    def test_graph_and_rules_are_deterministic_and_evidence_backed(self):
        import collector, json, sqlite3
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / 'test.sqlite'
            collector.init_db(db)
            trades = [dict(id=str(i),signature=str(i),wallet=w,mint='mint',side=s,timestamp='2026-09-22T00:00:0'+str(i)+'Z',verified=True) for i,(w,s) in enumerate([('a','buy'),('b','buy'),('a','sell')])]
            with sqlite3.connect(db) as c:
                c.executemany('INSERT INTO trades VALUES(?,?,?)',[(t['id'],t['timestamp'],json.dumps(t)) for t in trades])
            first = analytics.snapshot(db)
            self.assertEqual(first,analytics.snapshot(db))
            self.assertEqual(len(first['graph']['edges']),2)
            self.assertEqual({d['kind'] for d in first['decisions']},{'FIRST_SEEN','CO_BUY','SELL_OBSERVED'})
            self.assertTrue(all(set(d['evidence']) <= {'0','1','2'} for d in first['decisions']))
            self.assertTrue(all(t['pnl'] is None and not t['historyComplete'] for t in first['traders']))

    def test_empty_database_is_honest_starting_state(self):
        with tempfile.TemporaryDirectory() as d:
            result = analytics.snapshot(Path(d) / 'new.sqlite')
        self.assertEqual(result['version'], 'trenchnet-v1')
        self.assertEqual(result['status']['collector'], 'starting')
        self.assertEqual(result['trades'], [])
        self.assertEqual(result['analysis'], {'engine':'rules','version':'v2','paidModels':False})
        self.assertNotIn('models', result['status'])
        self.assertIsNone(result['updatedAt'])
