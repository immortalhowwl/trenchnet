import test from 'node:test';
import assert from 'node:assert/strict';
import * as helpers from '../web/utils.mjs';
test('price freshness is based on row timestamp, not global collector time',()=>{
 assert.equal(typeof helpers.marketFreshness,'function');
 assert.equal(helpers.marketFreshness({fetchedAt:'2026-01-01T00:00:00Z'},Date.parse('2026-01-01T00:11:00Z')),'stale');
 assert.equal(helpers.marketFreshness({fetchedAt:'2026-01-01T00:00:00Z'},Date.parse('2026-01-01T00:01:00Z')),'recent');
 assert.equal(helpers.marketFreshness({}),'unknown');
});

test('graph identifiers resolve to raw public addresses',()=>{
 assert.equal(typeof helpers.graphAddress,'function');
 assert.equal(helpers.graphAddress({id:'wallet:11111111111111111111111111111111',type:'wallet'}),'11111111111111111111111111111111');
 assert.equal(helpers.graphAddress({id:'token:So11111111111111111111111111111111111111112',type:'token'}),'So11111111111111111111111111111111111111112');
});
