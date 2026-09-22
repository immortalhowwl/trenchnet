"""Release-edge tests, offline only."""
import unittest
import telegram_bot as bot

class BotReleaseTests(unittest.TestCase):
    def test_message_includes_observation_time(self):
        import tempfile
        from pathlib import Path
        from test_telegram_bot import snap, W
        with tempfile.TemporaryDirectory() as d:
            b=bot.Bot(str(Path(d)/'b.db'),clock=lambda:1000)
            b.command(1,'/follow '+W); b.command(1,'/subscribe')
            b.clock=lambda:1002
            sent=[]
            def send(chat,text,markup):
                sent.append(text)
                return True
            source=snap()
            b.deliver(source,send)
            b.db.close()
            self.assertIn(source['trades'][0]['timestamp'],sent[0])

    def test_retry_after_is_not_shortened(self):
        transport=bot.Transport('123:TEST',clock=lambda:1000)
        transport.rate_limit({'parameters':{'retry_after':900}})
        self.assertGreaterEqual(transport.cooldown,1900)
