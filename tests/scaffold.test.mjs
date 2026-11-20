// Kiểm xương sống repo: các file bắt buộc có mặt và manifest hợp lệ.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const required = [
  'README.md', 'LICENSE', 'CLAUDE.md', 'AGENTS.md', 'GEMINI.md',
  'CODE_OF_CONDUCT.md', 'CONTRIBUTING.md', 'SECURITY.md',
  '.gitignore', '.dockerignore', '.editorconfig', '.ai42e.json',
  'docs/CHANGELOG.md', 'docs/JOURNAL.md', 'docs/ARCHITECTURE.md',
];

test('xương sống repo có đủ file bắt buộc', () => {
  for (const f of required) assert.ok(fs.existsSync(path.join(root, f)), `thiếu ${f}`);
});

test('.ai42e.json đúng định dạng', () => {
  const m = JSON.parse(fs.readFileSync(path.join(root, '.ai42e.json'), 'utf8'));
  assert.equal(m.integrationBranch, 'dev');
  assert.equal(typeof m.free, 'boolean');
});
