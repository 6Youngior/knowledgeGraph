import { DatabaseSync } from 'node:sqlite';
import { readFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const codeDir = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
export const PROJECT_ROOT = resolve(codeDir, '..');

export class TokenBudget {
  constructor({ path = join(PROJECT_ROOT, '.fingraph', 'usage.sqlite'), limit } = {}) {
    this.limit = Number(limit ?? process.env.FINGRAPH_LLM_TEST_TOKEN_LIMIT ?? 1000000);
    if (!Number.isSafeInteger(this.limit) || this.limit <= 0) throw new Error('Invalid token budget.');
    mkdirSync(dirname(path), { recursive: true });
    this.db = new DatabaseSync(path);
    this.db.exec('PRAGMA busy_timeout=5000; PRAGMA journal_mode=WAL;');
    this.db.exec(readFileSync(join(codeDir, 'llm_usage.sql'), 'utf8'));
  }

  charged() {
    return Number(this.db.prepare('SELECT COALESCE(SUM(COALESCE(total_tokens,reserved_tokens)),0) AS n FROM llm_requests').get().n);
  }

  reserve(model, purpose, inputBytes, maxOutputTokens, runId) {
    const reserved = Math.max(0, Number(inputBytes)) + Math.max(0, Number(maxOutputTokens)) + 1024;
    if (!Number.isSafeInteger(reserved)) throw new Error('Invalid request size.');
    const id = randomUUID();
    this.db.exec('BEGIN IMMEDIATE');
    try {
      if (this.charged() + reserved > this.limit) throw new Error('测试 token 预算不足，未发起调用。扩大额度前请先确认。');
      this.db.prepare('INSERT INTO llm_requests(request_id,run_id,model,purpose,started_at,reserved_tokens) VALUES(?,?,?,?,?,?)')
        .run(id, runId, model, purpose, new Date().toISOString(), reserved);
      this.db.exec('COMMIT');
      return id;
    } catch (error) {
      this.db.exec('ROLLBACK');
      throw error;
    }
  }

  complete(id, usage) {
    const input = Number(usage?.input ?? 0) + Number(usage?.cacheRead ?? 0) + Number(usage?.cacheWrite ?? 0);
    const output = Number(usage?.output ?? 0);
    const total = Number(usage?.totalTokens ?? input + output);
    if (!Number.isSafeInteger(total) || total <= 0) return this.uncertain(id);
    this.db.prepare("UPDATE llm_requests SET input_tokens=?,output_tokens=?,total_tokens=?,status='complete',completed_at=? WHERE request_id=? AND total_tokens IS NULL")
      .run(input, output, total, new Date().toISOString(), id);
  }

  uncertain(id) {
    this.db.prepare("UPDATE llm_requests SET status='uncertain' WHERE request_id=? AND total_tokens IS NULL").run(id);
  }

  snapshot() {
    const row = this.db.prepare('SELECT COUNT(*) AS requests,COALESCE(SUM(total_tokens),0) AS reported_tokens,COALESCE(SUM(CASE WHEN total_tokens IS NULL THEN reserved_tokens ELSE 0 END),0) AS reserved_tokens FROM llm_requests').get();
    return { ...row, limit: this.limit, remaining_tokens: this.limit - this.charged() };
  }

  close() { this.db.close(); }
}
