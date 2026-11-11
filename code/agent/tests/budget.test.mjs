import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { TokenBudget } from '../src/budget.mjs';
import { createUsageExtension } from '../extensions/usage.mjs';

function fixture(t, limit = 10000) {
  const dir = mkdtempSync(join(tmpdir(), 'fingraph-budget-'));
  const budget = new TokenBudget({ path: join(dir, 'usage.sqlite'), limit });
  t.after(() => { budget.close(); rmSync(dir, { recursive: true, force: true }); });
  return budget;
}

test('reservations block a second request before reported usage is known', t => {
  const budget = fixture(t, 4000);
  budget.reserve('model', 'test', 1000, 1000, 'run');
  assert.throws(() => budget.reserve('model', 'test', 0, 0, 'run'), /预算不足/);
  assert.equal(budget.snapshot().reserved_tokens, 3024);
});

test('completion includes cache input and is idempotent', t => {
  const budget = fixture(t);
  const id = budget.reserve('model', 'test', 100, 100, 'run');
  budget.complete(id, { input: 10, cacheRead: 20, output: 5, totalTokens: 35 });
  budget.complete(id, { input: 1000, output: 1000, totalTokens: 2000 });
  assert.equal(budget.snapshot().reported_tokens, 35);
  assert.equal(budget.snapshot().reserved_tokens, 0);
});

test('missing usage retains the reservation instead of counting the call as free', t => {
  const budget = fixture(t);
  const id = budget.reserve('model', 'test', 100, 100, 'run');
  budget.complete(id, {});
  assert.equal(budget.snapshot().reported_tokens, 0);
  assert.equal(budget.snapshot().reserved_tokens, 1224);
});

test('the extension explicitly aborts when Pi would otherwise swallow a hook error', async t => {
  const budget = fixture(t, 10);
  const handlers = new Map();
  createUsageExtension({ budget, modelId: 'model' })({
    on: (name, fn) => handlers.set(name, fn), registerCommand() {},
  });
  let aborted = false;
  await assert.rejects(handlers.get('before_provider_request')({ payload: {} }, {
    model: { id: 'model', provider: 'opencode-go' }, abort() { aborted = true; },
  }), /预算不足/);
  assert.equal(aborted, true);
  assert.equal(budget.snapshot().requests, 0);
});

test('model changes are rejected before reserving or sending a request', async t => {
  const budget = fixture(t);
  const handlers = new Map();
  createUsageExtension({ budget, modelId: 'authorized' })({
    on: (name, fn) => handlers.set(name, fn), registerCommand() {},
  });
  let aborted = false;
  await assert.rejects(handlers.get('before_provider_request')({ payload: {} }, {
    model: { id: 'other', provider: 'opencode-go' }, abort() { aborted = true; },
  }), /仅配置/);
  assert.equal(aborted, true);
  assert.equal(budget.snapshot().requests, 0);
});
