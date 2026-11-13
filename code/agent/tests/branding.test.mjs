import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, lstatSync, mkdtempSync, readFileSync, readdirSync, rmdirSync, unlinkSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { test } from 'node:test';
import { prepareBrandPackage } from '../src/brand-package.mjs';
import { PRODUCT_NAME } from '../src/branding.mjs';

test('Pi itself uses the project brand, profile and original assets', (t) => {
  const agent = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const dependency = join(agent, 'node_modules/@earendil-works/pi-coding-agent');
  const original = readFileSync(join(dependency, 'package.json'));
  const profile = mkdtempSync(resolve(agent, '../../.fingraph/brand-check-'));
  const directory = prepareBrandPackage(dependency, profile);
  t.after(() => {
    // Only unlink generated entries; never recursively traverse asset junctions.
    for (const name of readdirSync(directory)) {
      const path = join(directory, name);
      const stat = lstatSync(path);
      assert.ok(stat.isFile() || stat.isSymbolicLink());
      unlinkSync(path);
    }
    rmdirSync(directory);
    rmdirSync(profile);
  });
  assert.equal(prepareBrandPackage(dependency, profile), directory);
  const config = pathToFileURL(join(dependency, 'dist/config.js')).href;
  const script = `const c=await import(${JSON.stringify(config)}); console.log(JSON.stringify({name:c.APP_NAME,title:c.APP_TITLE,profile:c.getAgentDir(),themes:c.getThemesDir()}));`;
  const result = JSON.parse(execFileSync(process.execPath, ['--input-type=module', '-e', script], {
    encoding: 'utf8', env: { ...process.env, PI_PACKAGE_DIR: directory,
      [`${PRODUCT_NAME.toUpperCase()}_CODING_AGENT_DIR`]: profile },
  }));
  assert.equal(result.name, PRODUCT_NAME);
  assert.equal(result.title, PRODUCT_NAME);
  assert.equal(result.profile, profile);
  assert.ok(existsSync(join(result.themes, 'dark.json')));
  assert.deepEqual(readFileSync(join(dependency, 'package.json')), original);
});
