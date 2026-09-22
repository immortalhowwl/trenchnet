import unittest, base64, struct
import collector

class DecoderSafetyTests(unittest.TestCase):
    def fixture(self):
        fields=[{'name':n,'type':t} for n,t in [('mint','pubkey'),('sol_amount','u64'),('token_amount','u64'),('is_buy','bool'),('user','pubkey'),('timestamp','i64'),('quote_mint','pubkey'),('quote_amount','u64')]]
        discriminator=[189,219,127,211,78,230,97,238]
        idl={'address':collector.PROGRAM,'types':[{'name':'TradeEvent','type':{'fields':fields}}],'events':[{'name':'TradeEvent','discriminator':discriminator}]}
        def event(buy):
            raw=bytes(discriminator)+bytes(32)+struct.pack('<QQB',10**9,123,buy)+bytes(32)+struct.pack('<q',1700000000)+bytes(32)+struct.pack('<Q',0)
            return 'Program data: '+base64.b64encode(raw).decode()
        balance={'owner':collector.ZERO,'mint':collector.ZERO,'uiTokenAmount':{'amount':'1000','decimals':6}}
        logs=['Program Outer invoke [1]','Program Inner invoke [2]',f'Program {collector.PROGRAM} invoke [3]',event(1),f'Program {collector.PROGRAM} success',f'Program {collector.PROGRAM} invoke [3]',event(0),f'Program {collector.PROGRAM} success','Program Inner failed: custom program error: 0x1','Program Outer success']
        tx={'blockTime':1700000000,'transaction':{'signatures':['sig'],'message':{'accountKeys':[]}},'meta':{'err':None,'logMessages':logs,'preTokenBalances':[balance],'postTokenBalances':[balance]}}
        return tx,idl

    def test_rolled_back_nested_invocations_never_verified(self):
        tx,idl=self.fixture()
        self.assertEqual(collector.decode_transaction(tx,'sig',idl),[])

    def test_unclosed_invocation_never_verified(self):
        tx,idl=self.fixture()
        tx['meta']['logMessages']=[x for x in tx['meta']['logMessages'] if 'failed:' not in x and x!='Program Outer success']
        self.assertEqual(collector.decode_transaction(tx,'sig',idl),[])
