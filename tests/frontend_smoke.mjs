// 无第三方依赖的浏览器脚本离线回归：旧 Key 清理、独立 API、会话、429/502。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const html = readFileSync(path.join(root, 'web', 'resume.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
assert.ok(script, '简历页应包含可测试的脚本');

function setup() {
  const local = new Map([['qz_settings_v1', JSON.stringify({
    mode: 'byok', endpoint: 'https://preview-api.example.invalid',
    apiKey: 'fake-legacy-key', baseUrl: 'https://old.invalid', model: 'test',
  })]]);
  const session = new Map();
  const elements = new Map();
  const calls = [];
  const lookup = (id) => {
    if (!elements.has(id)) {
      const classes = new Set();
      elements.set(id, {
        value: '', textContent: '', innerHTML: '', disabled: false, checked: false,
        classList: {
          add: (name) => classes.add(name),
          remove: (name) => classes.delete(name),
          contains: (name) => classes.has(name),
          toggle: (name, value) => value ? classes.add(name) : classes.delete(name),
        },
      });
    }
    return elements.get(id);
  };
  const storage = (map) => ({
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => map.set(key, String(value)),
    removeItem: (key) => map.delete(key),
  });
  let response = 'ok';
  const json = (data, status = 200) => new Response(JSON.stringify(data), {
    status, headers: { 'Content-Type': 'application/json' },
  });
  const sandbox = {
    document: { getElementById: lookup, querySelectorAll: () => [] },
    localStorage: storage(local), sessionStorage: storage(session),
    location: { protocol: 'https:', hostname: 'campus-jobs-board.pages.dev' },
    URL, Response, AbortController, AbortSignal, setTimeout: () => 0, clearTimeout: () => {},
    window: {}, alert: () => {},
    fetch: async (url, options = {}) => {
      calls.push({ url, options });
      if (url.endsWith('/api/capabilities')) return json({ llm: true, invite_required: true, private_vault: false });
      if (url.endsWith('/api/invite/redeem')) return json({ access_token: 'synthetic-session' });
      if (url.endsWith('/api/quota')) return json({ model_calls_remaining: 2, model_calls_limit: 30 });
      if (url.endsWith('/api/resume')) {
        if (response === '429') return json({ detail: '今日平台模型调用额度已用完，请明天再试' }, 429);
        if (response === '502') return json({ detail: '模型生成失败，请稍后重试' }, 502);
        return json({ markdown: '# 测试', warnings: [] });
      }
      throw Error('意外 API 请求');
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(script, sandbox);
  return { sandbox, local, session, lookup, calls, setResponse: (next) => { response = next; } };
}

test('升级自动删除旧浏览器模型 Key，并拒绝非 HTTPS/带凭据的 API 地址', () => {
  const { sandbox, local } = setup();
  assert.deepEqual(JSON.parse(local.get('qz_settings_v1')),
                   { endpoint: 'https://preview-api.example.invalid' });
  assert.doesNotMatch(html, /id="s-key"|\.apiKey|\/chat\/completions/);
  assert.equal(vm.runInContext('serverBase()', sandbox), 'https://preview-api.example.invalid');
  for (const endpoint of ['http://public.example.invalid', 'https://user:pass@api.example.invalid',
                          'https://api.example.invalid/path', 'http://127.0.0.1:8000']) {
    assert.throws(() => vm.runInContext(`settings.endpoint = ${JSON.stringify(endpoint)}; serverBase()`, sandbox));
  }
});

test('跨域邀请码登录后携带令牌，请求额满/失败时显示服务端消息', async () => {
  const { sandbox, session, lookup, calls, setResponse } = setup();
  await vm.runInContext('detectService()', sandbox);
  assert.equal(lookup('inviteCard').classList.contains('hidden'), false);
  lookup('inviteCode').value = 'synthetic-invite';
  await lookup('redeemInvite').onclick();
  assert.equal(JSON.parse(session.get('qz_invite_session_v1')).endpoint,
               'https://preview-api.example.invalid');
  assert.match(lookup('quotaHint').textContent, /可用 2 次/);
  const request = () => vm.runInContext('postService("/api/resume", {source:"browser"}, 1000)', sandbox);
  assert.equal((await request()).status, 200);
  assert.equal(calls.at(-2).url, 'https://preview-api.example.invalid/api/resume');
  assert.equal(calls.at(-2).options.headers.Authorization, 'Bearer synthetic-session');
  setResponse('429');
  await assert.rejects(request(), /今日平台模型调用额度已用完/);
  setResponse('502');
  await assert.rejects(request(), /模型生成失败/);
  lookup('signOutInvite').onclick();
  assert.equal(session.has('qz_invite_session_v1'), false);
});
