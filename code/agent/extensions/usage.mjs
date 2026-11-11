import { randomUUID } from 'node:crypto';
import { TokenBudget } from '../src/budget.mjs';

export function createUsageExtension(options = {}) {
 return function usageExtension(pi) {
  const budget = options.budget ?? new TokenBudget(options.budgetOptions);
  const outputLimit = Math.max(128, Math.min(Number(options.maxOutputTokens ?? process.env.LLM_MAX_OUTPUT_TOKENS ?? 1024), 4096));
  const modelId = options.modelId ?? process.env.LLM_MODEL ?? 'deepseek-v4.1-flash';
  let requestId;
  let runId = randomUUID();
  let calls = 0;

  pi.registerCommand('usage', {
    description: '查看本项目测试用量',
    handler: async (_args, ctx) => {
      const s = budget.snapshot();
      ctx.ui.notify(`接口已报告 ${s.reported_tokens.toLocaleString()} token；未确认预留 ${s.reserved_tokens.toLocaleString()}；上限 ${s.limit.toLocaleString()}。`, 'info');
    },
  });

  pi.on('before_agent_start', async () => { runId = randomUUID(); calls = 0; });
  pi.on('before_provider_request', async (event, ctx) => {
   try {
    if (ctx.model?.provider !== 'opencode-go' || ctx.model?.id !== modelId) {
      throw new Error('当前环境仅配置了指定的 OpenCode Go 模型，请检查 .env 中的 LLM_MODEL。');
    }
    if (++calls > 6) throw new Error('本次研究已达到六次模型调用上限，请缩小问题或继续提问。');
    if (requestId) budget.uncertain(requestId);
    const payload = event.payload;
    if (payload && typeof payload === 'object') {
      payload.max_tokens = Math.min(Number(payload.max_tokens ?? outputLimit), outputLimit);
      delete payload.max_completion_tokens;
      payload.thinking = { type: 'disabled' };
    }
    const bytes = Buffer.byteLength(JSON.stringify(payload ?? {}), 'utf8');
    requestId = budget.reserve(ctx.model.id, 'fingraph_agent', bytes, outputLimit, runId);
    return payload;
   } catch (error) {
    // Pi reports payload-hook exceptions and continues. Abort the run explicitly
    // so an exhausted budget also cancels the provider's request signal.
    ctx.abort();
    throw error;
   }
  });

  pi.on('message_end', async event => {
    if (event.message?.role !== 'assistant' || !requestId) return;
    budget.complete(requestId, event.message.usage);
    requestId = undefined;
  });
  pi.on('session_shutdown', async () => {
    if (requestId) budget.uncertain(requestId);
    budget.close();
  });
 };
}

export default createUsageExtension();
