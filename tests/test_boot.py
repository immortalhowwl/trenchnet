import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import boot

class BootTests(unittest.TestCase):
    def test_root_prepares_volume_then_drops_privileges_before_serving(self):
        calls = []
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / 'volume'
            with patch.dict(os.environ, {'DB_PATH': str(folder / 'db.sqlite')}), \
                 patch('os.geteuid', return_value=0), \
                 patch('os.chown', side_effect=lambda *x: calls.append(('chown', x))), \
                 patch('os.setgroups', side_effect=lambda *x: calls.append(('groups', x))), \
                 patch('os.setgid', side_effect=lambda *x: calls.append(('gid', x))), \
                 patch('os.setuid', side_effect=lambda *x: calls.append(('uid', x))), \
                 patch('server.main', side_effect=lambda: calls.append(('serve', ()))):
                boot.main()
            self.assertTrue(folder.is_dir())
            self.assertEqual([x[0] for x in calls], ['chown', 'groups', 'gid', 'uid', 'serve'])
            self.assertEqual(calls[3][1], (10001,))
