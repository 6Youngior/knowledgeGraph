import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import {
  ModelRuntime, createAgentSession, DefaultResourceLoader,
  SessionManager, SettingsManager,
} from '@earendil-works/pi-coding-agent';
import { TokenBudget } from '../src/budget.mjs';
import { createUsageExtension } from '../extensions/usage.mjs';

test('a real Pi session sends no HTTP request when its token budget is exhausted', { timeout: 20000 }, async () => {
  const dir = mkdtempSync(join(tmpdir(), 'fingraph-budget-session-'));
  const budget = new TokenBudget({ path: join(dir, 'usage.sqlite'), limit: 10 });
  let requests = 0;
  const server = createServer((_req, res) => {
    requests++;
    res.writeHead(500, { 'content-type': 'application/json' });
    res.end('{"error":{"message":"A blocked request reached HTTP"}}');
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  let session;
  try {
    const runtime = await ModelRuntime.create({
      authPath: join(dir, 'auth.json'), modelsPath: null,
      modelsStorePath: join(dir, 'models-cache'), allowModelNetwork: false,
      refreshOnCreate: false,
    });
    runtime.registerProvider('opencode-go', {
      api: 'openai-completions', apiKey: 'dummy-local-test',
      baseUrl: `http://127.0.0.1:${server.address().port}/v1`,
      models: [{ id: 'budget-test', name: 'Local budget test', reasoning: false,
        input: ['text'], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 32768, maxTokens: 128 }],
    });
    const settingsManager = SettingsManager.inMemory({
      defaultProvider: 'opencode-go', defaultModel: 'budget-test',
      defaultThinkingLevel: 'off', retry: { enabled: false },
    });
    const resourceLoader = new DefaultResourceLoader({
      cwd: dir, agentDir: dir, settingsManager,
      noExtensions: true, noSkills: true, noContextFiles: true,
      noPromptTemplates: true, noThemes: true,
      extensionFactories: [createUsageExtension({ budget, modelId: 'budget-test' })],
    });
    await resourceLoader.reload();
    assert.equal(resourceLoader.getSkills().skills.length, 0);
    assert.equal(resourceLoader.getAgentsFiles().agentsFiles.length, 0);
    ({ session } = await createAgentSession({
      cwd: dir, agentDir: dir, modelRuntime: runtime,
      model: runtime.getModel('opencode-go', 'budget-test'),
      settingsManager, resourceLoader, noTools: 'all', thinkingLevel: 'off',
      sessionManager: SessionManager.inMemory(dir),
    }));
    const messages = [];
    session.subscribe(event => {
      if (event.type === 'message_end' && event.message.role === 'assistant') messages.push(event.message);
    });
    await session.prompt('This request must be blocked locally.');
    assert.equal(requests, 0);
    assert.equal(budget.snapshot().requests, 0);
    assert.ok(messages.some(m => m.stopReason === 'aborted'), 'the provider run should be aborted');
  } finally {
    session?.dispose();
    budget.close();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    rmSync(dir, { recursive: true, force: true });
  }
});
