"""Independent release invariants against an old-schema database."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
import telegram_bot as bot


class UpgradeTests(unittest.TestCase):
    def test_legacy_state_survives_upgrade_and_start(self):
        with tempfile.TemporaryDirectory() as d:
            p=str(Path(d)/'legacy.sqlite')
            c=sqlite3.connect(p)
            c.executescript('''
                CREATE TABLE recipients(chat INTEGER PRIMARY KEY,active INTEGER DEFAULT 0,since REAL DEFAULT 0);
                CREATE TABLE follows(chat INTEGER,wallet TEXT COLLATE BINARY,since REAL,PRIMARY KEY(chat,wallet));
                CREATE TABLE delivered(chat INTEGER,event TEXT,PRIMARY KEY(chat,event));
                CREATE TABLE state(key TEXT PRIMARY KEY,value INTEGER);
                INSERT INTO recipients VALUES(17,1,100);
                INSERT INTO recipients VALUES(18,0,90);
                INSERT INTO follows VALUES(17,'11111111111111111111111111111111',95);
                INSERT INTO delivered VALUES(17,'previous-event');
                INSERT INTO state VALUES('offset',900);
            ''')
            before={t:c.execute('SELECT * FROM '+t).fetchall() for t in ['recipients','follows','delivered','state']}
            c.close()
            b=bot.Bot(p,clock=lambda:1000)
            b.command(17,'/start');b.command(18,'/start')
            for table,expected in before.items():
                actual=[tuple(r) for r in b.db.execute('SELECT * FROM '+table)]
                self.assertEqual(actual,expected,table)
            self.assertEqual(b.offset(),900)
            b.db.close()

    def test_partial_snapshot_never_becomes_notification(self):
        from test_telegram_bot import snap,W
        with tempfile.TemporaryDirectory() as d:
            b=bot.Bot(str(Path(d)/'state.sqlite'),clock=lambda:1000)
            b.command(17,'/follow '+W);b.command(17,'/subscribe');b.clock=lambda:1002
            source=snap();source['status']['collector']='partial'
            sent=[]
            b.deliver(source,lambda *args:sent.append(args) or True)
            self.assertEqual(sent,[])
            b.db.close()
