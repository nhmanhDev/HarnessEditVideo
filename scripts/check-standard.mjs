#!/usr/bin/env node
// Kiểm một repo theo chuẩn trong Rules/Repo Scaffold.md và Rules/AI Repo Rules.md
// (manifest, Docker, cổng, test, CI, SEO web, đường dẫn tuyệt đối, file chỉ dẫn agent).
// Dùng: node check-repo-standard.mjs [đường-dẫn-repo] [--strict] [--diff <base>] [--vault <thư-mục-vault>]   (mặc định: thư mục hiện tại)
// Hai mức: FAIL (chuẩn bắt buộc, thoát mã 1) và WARN (chuẩn nâng cao và mục mới đang chuyển tiếp; không làm hỏng mã thoát).
// --strict (hoặc SB_STRICT=1): tính WARN như FAIL (dùng cho repo mới). Chỉ đọc file, không sửa gì.
// --diff <base>: đường dẫn tuyệt đối chỉ quét dòng thêm mới so với <base>, và đòi docs/CHANGELOG.md đổi khi đổi code.
// --vault <dir>: vault để đối chiếu Reference/Port Table.md (mặc định: tự nhận nếu script nằm trong vault).
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync, execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const args = process.argv.slice(2);
const opt = (name) => { const i = args.indexOf(name); return i >= 0 ? args.splice(i, 2)[1] : undefined; };
const diffBase = opt('--diff');
const vaultArg = opt('--vault');
const strict = args.includes('--strict') || process.env.SB_STRICT === '1';
const repo = path.resolve(args.find((a) => !a.startsWith('--')) || '.');
if (diffBase !== undefined && (!/^[\w./-]+$/.test(diffBase) || diffBase.startsWith('-'))) {
  console.log(`FAIL  --diff: base "${diffBase}" không hợp lệ (chỉ nhận chữ, số, . _ / -, không bắt đầu bằng -)`);
  process.exit(1);
}
const selfDir = path.dirname(fileURLToPath(import.meta.url));
const inVault = path.basename(selfDir) === '_Setup' && fs.existsSync(path.join(selfDir, '..', 'SecondBrain.md'));
const vault = vaultArg ? path.resolve(vaultArg) : inVault ? path.resolve(selfDir, '..') : '';

const out = [];
const add = (ok, msg, level = 'fail') => out.push({ ok, msg, level });
const warn = (ok, msg) => add(ok, msg, 'warn');
const p = (...s) => path.join(repo, ...s);
const has = (...s) => fs.existsSync(p(...s));
const read = (...s) => (has(...s) && fs.statSync(p(...s)).isFile() ? fs.readFileSync(p(...s), 'utf8') : '');
const git = (...a) => execFileSync('git', ['-C', repo, '-c', 'core.quotepath=off', ...a], { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024, stdio: ['ignore', 'pipe', 'ignore'] });
const lineOf = (text, idx) => text.slice(0, idx).split('\n').length;
const shortList = (a, n = 6) => a.slice(0, n).join(', ') + (a.length > n ? `, ... (+${a.length - n})` : '');

// Cổng mặc định của framework hay nền tảng: không được dùng (xem Reference/Port Table.md).
const DEFAULT_PORTS = new Set([3000, 3001, 4000, 4200, 5000, 5173, 7860, 8000, 8080, 8501, 8888, 9000]);
const isDefault = (n) => DEFAULT_PORTS.has(Number(n));

// ---- Manifest .ai42e.json (kind, free, port, integrationBranch) ----
const KINDS = ['web-public', 'web-internal', 'desktop', 'backend', 'static', 'lib'];
let manifest = null;
if (!has('.ai42e.json')) {
  warn(false, '.ai42e.json: thiếu manifest repo. Tạo từ _Skills/sb-new-repo/assets/ai42e.json (khai kind, free, port, integrationBranch) rồi đặt ở gốc repo');
} else {
  try {
    manifest = JSON.parse(read('.ai42e.json'));
    const errs = [];
    if (!KINDS.includes(manifest.kind)) errs.push(`kind phải thuộc ${KINDS.join('|')}`);
    if (typeof manifest.free !== 'boolean') errs.push('free phải là true/false');
    if (!(manifest.port === null || Number.isInteger(manifest.port))) errs.push('port phải là số hoặc null');
    if (typeof manifest.integrationBranch !== 'string' || !manifest.integrationBranch) errs.push('integrationBranch phải là chuỗi');
    add(errs.length === 0, `.ai42e.json: hợp lệ${errs.length ? ` (lỗi: ${errs.join('; ')})` : ` (kind=${manifest.kind}, port=${manifest.port}, nhánh=${manifest.integrationBranch})`}`);
    if (errs.length) manifest = { ...manifest, kind: KINDS.includes(manifest.kind) ? manifest.kind : undefined };
  } catch (e) {
    add(false, `.ai42e.json: không đọc được JSON (${e.message})`);
  }
}
const kind = manifest?.kind;
const port = manifest && Number.isInteger(manifest.port) ? manifest.port : null;
const branch = manifest?.integrationBranch || 'dev';
// desktop/static/lib không chạy bằng Docker: các mục Docker chỉ cảnh báo.
const dk = (ok, msg) => add(ok, msg, ['desktop', 'static', 'lib'].includes(kind) ? 'warn' : 'fail');

// ---- Dockerfile ----
const dockerfile = read('Dockerfile');
if (!dockerfile) {
  dk(false, 'Dockerfile: thiếu');
} else {
  const lines = dockerfile.split(/\r?\n/);
  const users = lines.map((l) => l.match(/^\s*USER\s+(\S+)/i)?.[1]).filter(Boolean);
  const lastUser = users[users.length - 1];
  dk(!!lastUser && !/^(root|0)(:|$)/.test(lastUser), 'Dockerfile: chạy bằng user thường (có USER không phải root)');
  dk(!/chmod\s+(-R\s+)?777/.test(dockerfile), 'Dockerfile: không chmod 777');
  const copyEnv = lines.findIndex((l) => /^\s*(COPY|ADD)\s+(--\S+\s+)*\.env(\s|$)/i.test(l));
  warn(copyEnv < 0, `Dockerfile: không COPY .env${copyEnv >= 0 ? ` (Dockerfile:${copyEnv + 1})` : ''}`);

  const stages = new Set();
  const badFrom = [];
  for (const l of lines) {
    const m = l.match(/^\s*FROM\s+(\S+)(?:\s+AS\s+(\S+))?/i);
    if (!m) continue;
    const [, image, alias] = m;
    if (alias) stages.add(alias.toLowerCase());
    if (stages.has(image.toLowerCase()) && !alias) continue;
    const pinned = image.includes('@sha256:') || (image.includes(':') && !image.endsWith(':latest'));
    if (!pinned) badFrom.push(image);
  }
  dk(badFrom.length === 0, `Dockerfile: base image có tag cụ thể, không dùng latest${badFrom.length ? ` (lỗi: ${badFrom.join(', ')})` : ''}`);

  const exposed = [...dockerfile.matchAll(/^\s*EXPOSE\s+(.+)$/gim)].flatMap((m) => m[1].split(/\s+/)).map((s) => s.replace(/\/\w+$/, ''));
  const envPort = dockerfile.match(/^\s*ENV\s+PORT[= ]\s*(\d+)/im)?.[1];
  warn(!!envPort, 'Dockerfile: có ENV PORT');
  const portsUsed = [...exposed, ...(envPort ? [envPort] : [])].filter((x) => /^\d+$/.test(x));
  const defaults = portsUsed.filter(isDefault);
  dk(defaults.length === 0, `Dockerfile: không dùng cổng mặc định${defaults.length ? ` (lỗi: ${[...new Set(defaults)].join(', ')})` : ''}`);
  if (envPort) dk(exposed.length === 0 || exposed.every((e) => e === envPort), `Dockerfile: EXPOSE khớp ENV PORT (${envPort})`);
  if (port) {
    if (envPort) dk(Number(envPort) === port, `Dockerfile: ENV PORT (${envPort}) khớp port trong .ai42e.json (${port})`);
    const wrong = exposed.filter((e) => /^\d+$/.test(e) && Number(e) !== port);
    dk(wrong.length === 0, `Dockerfile: mọi EXPOSE khớp port trong .ai42e.json (${port})${wrong.length ? ` (lỗi: ${wrong.join(', ')})` : ''}`);
  }
}
dk(has('.dockerignore'), '.dockerignore: có');

// ---- Compose ----
const composeFile = ['docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml'].find((f) => has(f));
if (!composeFile) {
  dk(false, 'docker-compose: thiếu');
} else {
  const compose = read(composeFile);
  dk(/^\s*healthcheck:/m.test(compose), `${composeFile}: có healthcheck`);
  warn(/^\s*restart:\s*["']?unless-stopped["']?\s*(#.*)?$/m.test(compose), `${composeFile}: restart: unless-stopped`);
  warn(/^\s*(mem_limit|cpus|mem_reservation):|^\s*limits:/m.test(compose), `${composeFile}: có giới hạn bộ nhớ/CPU (mem_limit, cpus hoặc deploy.resources.limits)`);
  const hostPorts = [];
  const containerPorts = [];
  const notLocal = [];
  let ctx = '';
  compose.split(/\r?\n/).forEach((l, i) => {
    const key = l.match(/^\s*([A-Za-z_]+):\s*$/)?.[1];
    if (key) ctx = key;
    const entry = ctx === 'ports' && l.match(/^\s*-\s*["']?(.+?)["']?\s*$/)?.[1];
    if (!entry) return;
    if (!/^(127\.0\.0\.1:|\$\{[A-Za-z_]\w*:-127\.0\.0\.1\}:)/.test(entry)) notLocal.push(`${composeFile}:${i + 1}`);
    const m = entry.match(/(\d+):(\d+)(?:\/\w+)?$/);
    if (m) { hostPorts.push(m[1], m[2]); containerPorts.push(Number(m[2])); }
  });
  warn(notLocal.length === 0, `${composeFile}: ports bind 127.0.0.1${notLocal.length ? ` (lỗi: ${shortList(notLocal)})` : ''}`);
  const bad = hostPorts.filter(isDefault);
  dk(bad.length === 0, `${composeFile}: không publish cổng mặc định${bad.length ? ` (lỗi: ${[...new Set(bad)].join(', ')})` : ''}`);
  if (port) dk(containerPorts.includes(port), `${composeFile}: có publish cổng container ${port} (port trong .ai42e.json)`);
}

// ---- Cổng so với Reference/Port Table.md của vault ----
if (port) {
  add(!isDefault(port), `Cổng ${port} (.ai42e.json): không phải cổng mặc định`);
  const tableFile = vault && path.join(vault, 'Reference', 'Port Table.md');
  if (tableFile && fs.existsSync(tableFile)) {
    const norm = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
    const me = norm(manifest.name || path.basename(repo));
    const rows = [];
    for (const l of fs.readFileSync(tableFile, 'utf8').split(/\r?\n/)) {
      const c = l.split('|').map((s) => s.trim());
      if (c.length < 4 || !c[1] || /^[-\s:]+$/.test(c[1])) continue;
      const name = c[1].replace(/\[\[|\]\]/g, '').replace(/\s*\(.*$/, '').trim();
      const ports = [...c[2].matchAll(/\b(\d{4,5})\b/g)].map((m) => Number(m[1]));
      if (name && ports.length) rows.push({ name, ports });
    }
    const other = rows.find((r) => norm(r.name) !== me && r.ports.includes(port));
    const mine = rows.filter((r) => norm(r.name) === me);
    if (other) add(false, `Port Table: cổng ${port} đã thuộc ${other.name}`);
    else if (mine.some((r) => r.ports.includes(port))) add(true, `Port Table: cổng ${port} khớp bảng`);
    else if (mine.length) warn(false, `Port Table: ${mine[0].name} ghi cổng ${mine[0].ports.join(', ')}, manifest khai ${port}`);
    else warn(false, `Port Table: cổng ${port} chưa có trong Reference/Port Table.md (thêm một dòng; nếu tên repo khác tên sản phẩm thì khai "name" trong .ai42e.json)`);
  }
}

// ---- Test, CI, .env ----
const hasTests = has('tests') || has('test') || has('__tests__');
add(hasTests, 'tests/: có');
// App trong thư mục con: GitHub chỉ đọc .github ở gốc git, nên tìm ở đó nếu repo không có.
let wfDir = p('.github', 'workflows');
if (!fs.existsSync(wfDir)) {
  try { const top = git('rev-parse', '--show-toplevel').trim(); if (top) wfDir = path.join(top, '.github', 'workflows'); } catch { /* không phải repo git */ }
}
const wf = fs.existsSync(wfDir) ? fs.readdirSync(wfDir).filter((f) => /\.ya?ml$/.test(f)) : [];
add(wf.length > 0, 'CI: có workflow trong .github/workflows');
if (wf.length) {
  const wfText = wf.map((f) => fs.readFileSync(path.join(wfDir, f), 'utf8'));
  const tokenRe = new RegExp(`(^|[\\s\\[,'"-])${branch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|[\\s\\],'"])`);
  // Đạt khi có pull_request không giới hạn nhánh (mọi PR) hoặc có branches chứa nhánh tích hợp.
  const onPr = wfText.some((t) => {
    if (/^\s*on\s*:\s*(pull_request|\[[^\]]*\bpull_request\b[^\]]*\])\s*(#.*)?$/m.test(t) || /^\s*-\s*pull_request\s*$/m.test(t)) return true;
    const ls = t.split(/\r?\n/);
    return ls.some((l, i) => {
      if (!/^\s*pull_request\s*:/.test(l)) return false;
      const indent = l.match(/^\s*/)[0].length;
      const block = [l];
      for (const x of ls.slice(i + 1, i + 8)) { if (x.trim() && x.match(/^\s*/)[0].length <= indent) break; block.push(x); }
      if (!block.some((x) => /^\s*branches\s*:/.test(x))) return true;
      return block.some((x) => (/branches/.test(x) || /^\s*-\s/.test(x)) && tokenRe.test(x));
    });
  });
  warn(onPr, `CI: có workflow chạy khi mở PR vào ${branch} (pull_request.branches)`);
  warn(wfText.some((t) => t.includes('scripts/check-standard.mjs')), 'CI: có bước chạy scripts/check-standard.mjs');
  warn(wfText.some((t) => /gitleaks|trufflehog/i.test(t)), 'CI: có quét secret (gitleaks hoặc trufflehog)');
  if (dockerfile) warn(wfText.some((t) => /trivy/i.test(t)), 'CI: có quét image (trivy) vì repo có Dockerfile');
  // Ghim action theo commit SHA 40 ký tự (tag có thể bị đổi trỏ). Bỏ qua action cục bộ (./) và docker://.
  const unpinned = [];
  wf.forEach((f, i) => wfText[i].split(/\r?\n/).forEach((l, n) => {
    const m = l.match(/^\s*-?\s*uses:\s*["']?([^\s"'#]+)/);
    if (m && !/^(\.\/|docker:\/\/)/.test(m[1]) && !/@[0-9a-f]{40}$/.test(m[1])) unpinned.push(`${f}:${n + 1}`);
  }));
  warn(unpinned.length === 0, `CI: mọi action ghim theo commit SHA, không dùng tag${unpinned.length ? ` (lỗi: ${shortList(unpinned)})` : ''}`);
}
if (inVault && has('scripts', 'check-standard.mjs')) {
  const h = (file) => crypto.createHash('sha256').update(fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n')).digest('hex');
  warn(h(path.join(selfDir, 'check-repo-standard.mjs')) === h(p('scripts', 'check-standard.mjs')), 'scripts/check-standard.mjs: giống bản trong vault (lệch thì chép lại từ _Setup/check-repo-standard.mjs)');
}
add(has('.env.example'), '.env.example: có');

// ---- Web công khai (chỉ khi là dự án Next.js) ----
let pkg = {};
try { pkg = JSON.parse(read('package.json') || '{}'); } catch { /* bỏ qua */ }
const deps = { ...pkg.dependencies, ...pkg.devDependencies };
if (deps.next) {
  const anyOf = (...paths) => paths.some((x) => has(...x.split('/')));
  add(anyOf('public/robots.txt', 'src/app/robots.ts', 'src/app/robots.js', 'app/robots.ts', 'app/robots.js'), 'SEO: có robots (Next.js)');
  add(anyOf('public/sitemap.xml', 'src/app/sitemap.ts', 'src/app/sitemap.js', 'app/sitemap.ts', 'app/sitemap.js'), 'SEO: có sitemap (Next.js)');
}

// ---- Đường dẫn tuyệt đối theo máy: file git theo dõi + file mới chưa ignore (hoặc chỉ dòng thêm mới với --diff) ----
// /Users và /home phân biệt hoa thường (tránh nhầm route /api/admin/users/{id}/); /home/<user mặc định của image>/ bỏ qua.
// Ổ đĩa: không dính chữ đứng trước ("này:\n" trong chuỗi JS), không tính "\n"/"\t"/"\r" và chỗ giữ chỗ ("C:\...").
const DRV = String.raw`(?<![\p{L}\p{N}_])[A-Za-z]:(?:\\(?![nrt](?![A-Za-z0-9_]))|/)(?!\.\.\.|…)`;
const DRIVE_RE = new RegExp(String.raw`(?:${DRV}|file:///[A-Za-z]:/)`, 'u');
const ABS_RE = new RegExp(String.raw`(?:${DRV}|file:///[A-Za-z]:/|/(?:Users|home)/(?!(?:user|node|app|appuser|runner|ubuntu)/)(?![.…]+/)[^/\s"'<>]+/)`, 'u');
const isInfra = (f) => /(^|\/)(Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|compose\.ya?ml)$/.test(f) || f.startsWith('.github/');
const reFor = (f) => (isInfra(f) ? DRIVE_RE : ABS_RE);
const globRe = (g) => new RegExp('^' + g.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*\*/g, '\0').replace(/\*/g, '[^/]*').replace(/\?/g, '[^/]').replace(/\0/g, '.*') + '$');
const allowRe = read('.sb-allow-abs').split(/\r?\n/).map((s) => s.trim()).filter((s) => s && !s.startsWith('#')).map(globRe);
const allowed = (file, n) => allowRe.some((r) => r.test(file) || r.test(`${file}:${n}`));
// Một bộ lọc file cho cả hai chế độ.
const SKIP_FILE = /(^|\/)(node_modules|dist|build)\/|(^|\/)(package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml|bun\.lockb|[\w.-]+\.lock)$|^docs\/(CHANGELOG|JOURNAL)\.md$|^\.sb-allow-abs$/;
// Trả về [{file, n, text}] các dòng khớp.
function absHits() {
  const res = [];
  if (diffBase) {
    let cur = null;
    let n = 0;
    for (const l of git('diff', '-U0', '--no-color', `${diffBase}...HEAD`).split('\n')) {
      if (l.startsWith('+++ ')) { cur = l.startsWith('+++ b/') && !SKIP_FILE.test(l.slice(6)) ? l.slice(6) : null; continue; }
      const h = l.match(/^@@ -\S+ \+(\d+)/);
      if (h) { n = Number(h[1]); continue; }
      if (cur && l.startsWith('+')) { if (reFor(cur).test(l)) res.push({ file: cur, n, text: l.slice(1) }); n++; }
    }
    return res;
  }
  for (const f of new Set(git('ls-files', '-co', '--exclude-standard', '-z').split('\0').filter(Boolean))) {
    if (SKIP_FILE.test(f)) continue;
    let st;
    try { st = fs.lstatSync(p(f)); } catch { continue; }
    if (!st.isFile() || st.size > 1024 * 1024) continue;
    const buf = fs.readFileSync(p(f));
    if (buf.subarray(0, 8000).includes(0)) continue;
    const content = buf.toString('utf8');
    if (!reFor(f).test(content)) continue;
    content.split(/\r?\n/).forEach((text, i) => { if (reFor(f).test(text)) res.push({ file: f, n: i + 1, text }); });
  }
  return res;
}
try {
  const all = absHits().filter((x) => !allowed(x.file, x.n));
  const inTests = (x) => /^(tests?|__tests__)\//.test(x.file);
  const fmt = (a) => a.map((x) => `${x.file}:${x.n}`);
  const hard = fmt(all.filter((x) => !inTests(x)));
  const soft = fmt(all.filter(inTests));
  add(hard.length === 0, `Không có đường dẫn tuyệt đối theo máy${diffBase ? ` (dòng thêm mới so với ${diffBase})` : ''}${hard.length ? ` (lỗi: ${shortList(hard, 10)})` : ''}`);
  if (soft.length) warn(false, `Đường dẫn tuyệt đối trong tests/ (${shortList(soft, 10)})`);
} catch {
  warn(false, `Đường dẫn tuyệt đối: không quét được (cần repo git${diffBase ? ` và base "${diffBase}" hợp lệ` : ''})`);
}

// ---- File chỉ dẫn agent (CLAUDE/AGENTS/GEMINI) ----
const sections = {};
for (const f of ['CLAUDE.md', 'AGENTS.md', 'GEMINI.md'].filter((x) => has(x))) {
  const t = read(f).replace(/\r\n/g, '\n');
  const hits = (re) => [...new Set([...t.matchAll(re)].map((m) => `${f}:${lineOf(t, m.index)}`))];
  const pathHits = hits(/@[A-Za-z]:\\|SecondBrain[\\/]SecondBrain\.md/g);
  add(pathHits.length === 0, `${f}: không trỏ tới đường dẫn máy/vault${pathHits.length ? ` (lỗi: ${shortList(pathHits)})` : ''}`);
  const copied = hits(/Behavioral guidelines|KHÔNG tự code|Workflow bắt buộc|Đầu MỖI phiên/g);
  warn(copied.length === 0, `${f}: không chép luật chung (đã có ở global/AI Repo Rules)${copied.length ? ` (lỗi: ${shortList(copied)})` : ''}`);
  const trimmed = t
    .replace(/<!--\s*gitnexus:start\s*-->[\s\S]*?<!--\s*gitnexus:end\s*-->/g, '')
    .replace(/<!--\s*BEGIN:nextjs[^>]*-->[\s\S]*?<!--\s*END:nextjs[^>]*-->/g, '');
  warn(trimmed.length <= 3000, `${f}: ngắn gọn (${trimmed.length}/3000 ký tự, không tính khối GitNexus/Next.js)`);
  const refs = [];
  const refsIgnored = [];
  const seen = new Set();
  for (const m of t.matchAll(/`([^`\n]+)`/g)) {
    const tok = m[1].trim().split(/\s+/)[0].replace(/[.,;:)]+$/, '').replace(/:\d+$/, '');
    if (seen.has(tok) || /[<>*{}$|]|\.\.\.|…/.test(tok)) continue;
    if (/^_Templates\//.test(tok)) { seen.add(tok); refs.push(`${f}:${lineOf(t, m.index)} ${tok} (đường dẫn vault cũ)`); continue; }
    if (/^(\.claude|\.codex|docs|scripts)\//.test(tok) && !has(...tok.replace(/\/$/, '').split('/'))) {
      seen.add(tok);
      const ref = `${f}:${lineOf(t, m.index)} ${tok}`;
      let ignored = false;
      try { git('check-ignore', '-q', tok.replace(/\/$/, '')); ignored = true; } catch { /* không bị ignore */ }
      (ignored ? refsIgnored : refs).push(ref);
    }
  }
  if (refsIgnored.length) warn(false, `${f}: nhắc tới đường dẫn bị gitignore, chưa có trên máy này (${shortList(refsIgnored, 8)})`);
  warn(refs.length === 0, `${f}: đường dẫn nhắc tới đều tồn tại${refs.length ? ` (lỗi: ${shortList(refs, 8)})` : ''}`);
  const sec = t.match(/^## Quy tắc dự án[^\n]*\n([\s\S]*?)(?=^## |(?![\s\S]))/m)?.[1] ?? '';
  if (!/^\s*@(CLAUDE|AGENTS|GEMINI)\.md\s*$/.test(t)) sections[f] = sec.replace(/\s+/g, ' ').trim();
}
const secNames = Object.keys(sections);
if (secNames.length > 1) warn(secNames.every((f) => sections[f] === sections[secNames[0]]), `Agent files: mục "Quy tắc dự án" giống nhau giữa ${secNames.join(', ')}`);

// ---- CHANGELOG theo thay đổi (chỉ với --diff) ----
if (diffBase) {
  try {
    const files = git('diff', '--name-only', `${diffBase}...HEAD`).split('\n').filter(Boolean);
    const code = files.filter((f) => !/\.md$/i.test(f) && !/^(docs|tests?|__tests__|\.github)\//.test(f) && !SKIP_FILE.test(f));
    const skip = /^Changelog:\s*skip\s*$/im.test(git('log', '--format=%B', `${diffBase}..HEAD`));
    if (code.length && !files.includes('docs/CHANGELOG.md') && !skip) add(false, `CHANGELOG: có đổi code (${shortList(code, 3)}) mà docs/CHANGELOG.md không đổi (bỏ qua bằng trailer "Changelog: skip")`);
    else add(true, `CHANGELOG: cập nhật cùng thay đổi code so với ${diffBase}`);
  } catch {
    warn(false, `CHANGELOG: không so được với base "${diffBase}"`);
  }
}

// ---- Chuẩn nâng cao (WARN): xương sống, tên, lint, phụ thuộc, mẫu PR, nhánh ----
const rootEnts = fs.readdirSync(repo, { withFileTypes: true });
const SPINE = ['README.md', 'CLAUDE.md', 'AGENTS.md', 'GEMINI.md', 'CODE_OF_CONDUCT.md', 'CONTRIBUTING.md', 'SECURITY.md', 'docs/CHANGELOG.md', 'docs/JOURNAL.md', 'docs/ARCHITECTURE.md', '.gitignore'];
const missingSpine = SPINE.filter((f) => !has(...f.split('/')));
if (!rootEnts.some((e) => e.isFile() && /^LICENSE(\.\w+)?$/i.test(e.name))) missingSpine.unshift('LICENSE');
warn(missingSpine.length === 0, `Xương sống: đủ file chuẩn${missingSpine.length ? ` (thiếu: ${missingSpine.join(', ')})` : ''}`);

let originName = '';
try { originName = fs.readFileSync(p('.git', 'config'), 'utf8').match(/url\s*=\s*\S*\/([^/\s]+?)(?:\.git)?\s*$/m)?.[1] || ''; } catch { /* không phải repo git thường */ }
const repoName = originName || path.basename(repo);
warn(/^[a-z0-9]+(-[a-z0-9]+)*$/.test(repoName), `Tên repo kebab-case (repo mới; repo cũ giữ tên): ${repoName}`);

const badDirs = rootEnts.filter((e) => e.isDirectory() && !e.name.startsWith('.') && e.name !== 'node_modules' && !/^[a-z0-9]+([-_][a-z0-9]+)*$/.test(e.name)).map((e) => e.name);
warn(badDirs.length === 0, `Tên thư mục cấp 1 chữ thường, kebab-case${badDirs.length ? ` (sai: ${badDirs.join(', ')})` : ''}`);

const CLUTTER = /\.(log|zip|bak|tmp|pdf|xlsx?|docx?|pptx?|jpe?g|png|ico|gif|py|c?js|mjs)$/i;
const OK_FILE = /^(setup\.py|conftest\.py|manage\.py|(index|server|app|main)\.(c|m)?js|.*\.config\.(c|m)?js|.*\.d\.ts)$/i;
const clutter = rootEnts.filter((e) => e.isFile() && !e.name.startsWith('.') && CLUTTER.test(e.name) && !OK_FILE.test(e.name)).map((e) => e.name);
warn(clutter.length === 0, `Gốc repo không có file lạ (log, zip, ảnh, script lẻ)${clutter.length ? ` (thấy: ${clutter.slice(0, 6).join(', ')})` : ''}`);

const SUB = ['', 'web', 'frontend', 'backend', 'app'];
const at = (d, n) => [d, n].filter(Boolean);
const anyIn = (names) => SUB.some((d) => names.some((n) => has(...at(d, n))));
const pyProj = SUB.some((d) => has(...at(d, 'pyproject.toml')) || has(...at(d, 'requirements.txt')));
const jsProj = SUB.some((d) => has(...at(d, 'package.json')));
if (pyProj) {
  const ruff = anyIn(['ruff.toml', '.ruff.toml']) || SUB.some((d) => /\[tool\.ruff/.test(read(...at(d, 'pyproject.toml'))));
  warn(ruff, 'Python: có cấu hình lint và format (ruff)');
}
if (jsProj) {
  warn(anyIn(['eslint.config.js', 'eslint.config.mjs', 'eslint.config.cjs', 'eslint.config.ts', '.eslintrc', '.eslintrc.json', '.eslintrc.js', '.eslintrc.cjs', 'biome.json', 'biome.jsonc']), 'JS/TS: có cấu hình lint (ESLint hoặc Biome)');
}
warn(has('.editorconfig'), '.editorconfig: có');
if (pyProj || jsProj) warn(has('.github', 'dependabot.yml') || has('.github', 'dependabot.yaml') || has('renovate.json') || has('.github', 'renovate.json'), 'Cập nhật phụ thuộc tự động (Dependabot hoặc Renovate)');
warn(has('.github', 'pull_request_template.md') || has('.github', 'PULL_REQUEST_TEMPLATE.md'), 'Mẫu PR: .github/pull_request_template.md');

try {
  const heads = new Set();
  const addRefs = (dir, pre) => { for (const e of fs.readdirSync(dir, { withFileTypes: true })) { if (e.isDirectory()) addRefs(path.join(dir, e.name), `${pre}${e.name}/`); else heads.add(pre + e.name); } };
  if (has('.git', 'refs', 'heads')) addRefs(p('.git', 'refs', 'heads'), '');
  if (has('.git', 'packed-refs')) for (const l of read('.git', 'packed-refs').split(/\r?\n/)) { const m = l.match(/ refs\/heads\/(\S+)/); if (m) heads.add(m[1]); }
  const okBranch = /^(main|dev|(feat|fix|chore|docs|refactor|test|ci|perf|spike|agent|codex)\/[a-z0-9][a-z0-9./_-]*)$/;
  const badBranch = [...heads].filter((b) => !okBranch.test(b));
  warn(badBranch.length === 0, `Tên nhánh theo loại/mô-tả (main, dev, feat/…, fix/…)${badBranch.length ? ` (${badBranch.length} nhánh lệch, VD: ${badBranch.slice(0, 4).join(', ')})` : ''}`);
} catch { /* không đọc được nhánh */ }

// Tên file và thư mục (chỉ file Git đang theo dõi) bằng tiếng Anh không dấu, không khoảng trắng: Rules/Naming Conventions.
{
  const ls = spawnSync('git', ['-C', repo, 'ls-files', '-z'], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  if (ls.status === 0 && ls.stdout) {
    const badNames = new Set();
    for (const f of ls.stdout.split('\0').filter(Boolean)) {
      const segs = f.split('/');
      const i = segs.findIndex((s) => /[^\x00-\x7F]| /.test(s));
      if (i >= 0) badNames.add(segs.slice(0, i + 1).join('/'));
    }
    const list = [...badNames];
    warn(list.length === 0, `Tên file và thư mục tiếng Anh, không dấu, không khoảng trắng${list.length ? ` (${list.length} chỗ sai, VD: ${list.slice(0, 3).join(', ')})` : ''}`);
  }
}

// Docs: CHANGELOG và JOURNAL đúng mẫu, giới hạn, độ mới (Rules/Docs Standard).
if (has('docs', 'CHANGELOG.md')) {
  const cl = read('docs', 'CHANGELOG.md').split(/\r?\n/);
  const cols = (cl.find((l) => l.startsWith('|')) || '').split('|').map((s) => s.trim().toLowerCase()).filter(Boolean);
  warn(cols[0] === 'ngày' && cols.some((c) => c.startsWith('nguyên nhân')) && cols.some((c) => c.startsWith('giải pháp')),
    `CHANGELOG: bảng cột "Ngày | Lỗi hoặc thay đổi | Nguyên nhân | Giải pháp" (đang là: ${cols.join(' | ') || 'không có bảng'})`);
  const dates = cl.map((l) => l.match(/^\|\s*(\d{4}-\d{2}-\d{2})\b/)?.[1]).filter(Boolean);
  warn(dates.every((d, i) => i === 0 || d <= dates[i - 1]), 'CHANGELOG: mục mới nhất ở đầu (ngày giảm dần)');
  warn(cl.length <= 400, `CHANGELOG: tối đa 400 dòng, chuyển phần cũ sang docs/archive/ (đang ${cl.length} dòng)`);
  const gitDate = (...a) => { const r = spawnSync('git', ['-C', repo, 'log', '-1', '--format=%cs', ...a], { encoding: 'utf8' }); return r.status === 0 ? r.stdout.trim() : ''; };
  const clDate = gitDate('--', 'docs/CHANGELOG.md');
  const lastDate = gitDate();
  if (clDate && lastDate) warn((new Date(lastDate) - new Date(clDate)) / 86400000 <= 14, `CHANGELOG: được cập nhật trong 14 ngày gần commit cuối (sửa lần cuối ${clDate}, commit cuối ${lastDate})`);
}
if (has('docs', 'JOURNAL.md')) {
  const jl = read('docs', 'JOURNAL.md').split(/\r?\n/);
  warn(jl.length <= 40, `JOURNAL: tối đa 40 dòng, xong việc thì xoá và ghi vào CHANGELOG (đang ${jl.length} dòng)`);
  const badHeads = jl.filter((l) => l.startsWith('### ') && !/^### \d{4}-\d{2}-\d{2} — \[[^\]]+\] — \S/.test(l));
  warn(badHeads.length === 0, `JOURNAL: mục dạng "### YYYY-MM-DD — [tool] — tiêu đề"${badHeads.length ? ` (${badHeads.length} mục sai)` : ''}`);
}

// ---- In kết quả ----
let fail = 0, warnN = 0, warnTotal = 0;
console.log(`Repo: ${path.basename(repo)}`);
for (const r of out) {
  if (r.level === 'warn') warnTotal++;
  if (r.ok) { console.log(`PASS  ${r.msg}`); continue; }
  if (r.level === 'warn' && !strict) { warnN++; console.log(`WARN  ${r.msg}`); } else { fail++; console.log(`FAIL  ${r.msg}`); }
}
const failTotal = out.length - warnTotal + (strict ? warnTotal : 0);
console.log(`${failTotal - fail}/${failTotal} đạt, ${fail} lỗi.${warnTotal && !strict ? ` Chuẩn nâng cao: ${warnTotal - warnN}/${warnTotal} đạt, ${warnN} cảnh báo.` : ''}`);
process.exit(fail ? 1 : 0);
