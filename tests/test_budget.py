import importlib.util
import unittest

class BudgetTests(unittest.TestCase):
    def test_time_and_spend_fail_closed(self):
        self.assertIsNotNone(importlib.util.find_spec('ops.budget_guard'))
        from ops.budget_guard import stop_reason
        self.assertIsNone(stop_reason(0.1, 100, 200))
        self.assertEqual(stop_reason(3.5, 100, 200), 'budget')
        self.assertEqual(stop_reason(0.1, 200, 200), 'time')
        self.assertEqual(stop_reason(None, 100, 200), 'billing_unavailable')
        self.assertEqual(stop_reason(float('nan'), 100, 200), 'billing_unavailable')
