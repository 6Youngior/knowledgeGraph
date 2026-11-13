import { existsSync, lstatSync, mkdirSync, readFileSync, readlinkSync, symlinkSync, unlinkSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { PRODUCT_NAME } from './branding.mjs';

// Pi resolves its app name and assets through PI_PACKAGE_DIR. Keep our
// metadata in the project profile and share the untouched dependency assets.
export function prepareBrandPackage(dependencyRoot, profile) {
  const destination = join(profile, 'brand-package');
  mkdirSync(destination, { recursive: true });
  const original = JSON.parse(readFileSync(join(dependencyRoot, 'package.json'), 'utf8'));
  const metadata = join(destination, 'package.json');
  const previous = existsSync(metadata) ? JSON.parse(readFileSync(metadata, 'utf8')) : undefined;
  const owned = previous?.fingraphRuntime === true;
  for (const name of ['dist', 'docs', 'examples', 'README.md', 'CHANGELOG.md']) {
    const source = resolve(dependencyRoot, name);
    if (!existsSync(source)) continue;
    const target = join(destination, name);
    const directory = lstatSync(source).isDirectory();
    const stat = lstatSync(target, { throwIfNoEntry: false });
    if (stat) {
      // Remove only a generated link if the project was moved. Never replace
      // a regular file or directory, or delete dependency assets.
      if (!stat.isSymbolicLink()) {
        if (!directory && owned) { writeFileSync(target, readFileSync(source)); continue; }
        if (!directory && readFileSync(target).equals(readFileSync(source))) continue;
        throw new Error(`品牌资源路径已被其他文件占用：${target}`);
      }
      if (resolve(destination, readlinkSync(target)) === source) continue;
      unlinkSync(target);
    }
    if (directory) symlinkSync(source, target, process.platform === 'win32' ? 'junction' : 'dir');
    else writeFileSync(target, readFileSync(source));
  }
  writeFileSync(metadata, JSON.stringify({
    ...original,
    fingraphRuntime: true,
    piConfig: { ...original.piConfig, name: PRODUCT_NAME },
  }, null, 2) + '\n');
  return destination;
}
