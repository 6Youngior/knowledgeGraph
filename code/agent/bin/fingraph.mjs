#!/usr/bin/env node
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { PRODUCT_NAME } from '../src/branding.mjs';
import { prepareBrandPackage } from '../src/brand-package.mjs';

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = resolve(packageRoot, '../..');
const args = process.argv.slice(2);
const [nodeMajor, nodeMinor] = process.versions.node.split('.').map(Number);
if (nodeMajor < 22 || (nodeMajor === 22 && nodeMinor < 19)) {
  console.error(`${PRODUCT_NAME} 需要 Node.js 22.19 或更新版本。`);
  process.exit(2);
}

if (args.includes('--help') || args.includes('-h')) {
  console.log('FinGragh Agent\n\n项目内启动：.\\fingraph.ps1\n首次安装：.\\fingraph.ps1 -Setup\n检查配置：.\\fingraph.ps1 -Check\n\n终端命令：/web 打开研究页，/usage 查看测试用量，/model 查看模型。');
  process.exit(0);
}
if (existsSync(join(root, '.env'))) process.loadEnvFile(join(root, '.env'));
const model = process.env.LLM_MODEL || 'deepseek-v4.1-flash';
const apiKey = process.env.LLM_API_KEY;
const python = process.env.FINGRAPH_PYTHON || join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const piCli = join(packageRoot, 'node_modules', '@earendil-works', 'pi-coding-agent', 'dist', 'bundle', 'cli.js');
const profile = join(root, '.fingraph', 'agent');
const asOf = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Shanghai' });
const port = Number(process.env.FINGRAPH_PORT || 8017);
const maxTokens = Math.max(128, Math.min(Number(process.env.LLM_MAX_OUTPUT_TOKENS || 1024), 4096));

if (!existsSync(piCli) || !existsSync(python)) {
  console.error('项目依赖尚未安装，请运行 .\\fingraph.ps1 -Setup。');
  process.exit(2);
}
if (!apiKey) {
  console.error('请复制 .env.example 为 .env，填写模型接口和密钥后启动。');
  process.exit(2);
}

mkdirSync(profile, { recursive: true });
const brandPackage = prepareBrandPackage(dirname(dirname(dirname(piCli))), profile);
writeFileSync(join(profile, 'settings.json'), JSON.stringify({
  defaultProvider: 'opencode-go', defaultModel: model, defaultThinkingLevel: 'off',
  retry: { enabled: false }, defaultTools: [], quietStartup: true,
  theme: 'fingraph-gold',
}, null, 2));
writeFileSync(join(profile, 'models.json'), JSON.stringify({ providers: {
  'opencode-go': { modelOverrides: { [model]: {
    maxTokens, contextWindow: 32768, samplingParams: { thinking: { type: 'disabled' } },
  } } },
} }, null, 2));
writeFileSync(join(profile, 'mcp.json'), JSON.stringify({
  mcpServers: { fingraph: {
    command: python, args: [join(root, 'code', 'mcp_server.py')], cwd: root,
    env: { FINGRAPH_AS_OF: asOf }, exposure: 'direct',
  } }, autoEnableCodemode: false,
}, null, 2));

if (args.includes('--check')) {
  console.log(JSON.stringify({
    project: PRODUCT_NAME, model, modelConfigured: Boolean(apiKey),
    profile, dependency: piCli, python,
    web: `http://127.0.0.1:${port}`, asOf,
    note: '配置检查不产生模型调用。',
  }, null, 2));
  process.exit(0);
}

const env = {
  ...process.env,
  OPENCODE_API_KEY: apiKey,
  PI_CODING_AGENT_DIR: profile,
  PI_CODING_AGENT_SESSION_DIR: join(profile, 'sessions'),
  PI_PACKAGE_DIR: brandPackage,
  [`${PRODUCT_NAME.toUpperCase()}_CODING_AGENT_DIR`]: profile,
  [`${PRODUCT_NAME.toUpperCase()}_CODING_AGENT_SESSION_DIR`]: join(profile, 'sessions'),
  // FinGraph doesn't use coding tools or fd; skip optional catalog/tool downloads.
  PI_OFFLINE: '1',
  FINGRAPH_AS_OF: asOf,
  FINGRAPH_WEB_URL: `http://127.0.0.1:${port}`,
  FINGRAPH_PYTHON: python,
};
const child = spawn(process.execPath, [
  piCli, '--no-extensions', '--no-skills', '--no-context-files', '--no-prompt-templates', '--no-themes',
  '--theme', join(packageRoot, 'themes', 'fingraph-gold.json'), '--use-theme', 'fingraph-gold',
  '-e', 'builtin:mcp',
  '-e', join(packageRoot, 'extensions', 'fingraph.ts'),
  '-e', join(packageRoot, 'extensions', 'usage.mjs'),
  '--tools', 'mcp__fingraph__*',
  '--model', `opencode-go/${model}`, '--thinking', 'off',
  '--system-prompt', join(packageRoot, 'config', 'research.md'),
  ...args,
], { cwd: root, env, stdio: 'inherit' });
child.on('error', error => { console.error(`${PRODUCT_NAME} 启动失败：${error.message}`); process.exit(1); });
child.on('exit', code => process.exit(code ?? 1));
