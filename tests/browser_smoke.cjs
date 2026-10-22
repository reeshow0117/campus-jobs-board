// 需要 Playwright，默认使用已安装的 Edge。仅访问本机 browser_fixture 测试服务。
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const { mkdir, writeFile } = require('node:fs/promises');
const path = require('node:path');

(async () => {
  const output = path.resolve(__dirname, '../../.resume-platform-local/qa');
  await mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.QIUZHAO_TEST_BROWSER || 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:8765/');
    assert.equal(await page.title(), '校招简历定制系统');
    const fixture = await page.evaluate(async () => (await fetch('/__test_fixture')).json());
    await page.locator('#inviteCode').fill(fixture.invite);
    await page.locator('#redeemInvite').click();
    await page.waitForFunction(() => document.getElementById('quotaHint').textContent.includes('已登录'));
    await page.locator('#importFile').setInputFiles({name: 'synthetic.json', mimeType: 'application/json',
      buffer: Buffer.from(JSON.stringify({profile: fixture.profile, materials: fixture.materials}))});
    await page.waitForFunction(() => document.querySelectorAll('.material-item').length === 2);
    await page.locator('#photoFile').setInputFiles({name: 'photo.png', mimeType: 'image/png',
      buffer: Buffer.from(fixture.photo.split(',')[1], 'base64')});
    await page.locator('[data-tab="gen"]').click();
    await page.locator('#g-title').fill('产品经理');
    await page.locator('#g-jd').fill('负责需求分析和产品方案设计');
    await page.locator('#genBtn').click();
    await page.waitForFunction(() => !document.getElementById('resultCard').classList.contains('hidden'));
    await page.locator('#previewPdf').click();
    await page.waitForFunction(() => document.getElementById('pdfFrame').src.startsWith('blob:'));
    const downloadReady = page.waitForEvent('download');
    await page.locator('#dlPdf').click();
    const download = await downloadReady;
    await download.saveAs(path.join(output, 'synthetic-resume.pdf'));
    await page.screenshot({path: path.join(output, 'desktop.png'), fullPage: true});
    const q = await page.evaluate(async () => {
      const s = JSON.parse(sessionStorage.getItem('qz_invite_session_v1'));
      return (await fetch('/api/quota', {headers: {Authorization: `Bearer ${s.token}`}})).json();
    });
    assert.equal(q.model_calls_used, 3);
    // 编辑当前资料后，PDF 仍需引用生成时的素材快照。
    await page.locator('[data-tab="profile"]').click();
    await page.locator('#p-name').fill('修改后的姓名');
    await page.locator('#photoFile').setInputFiles([]);
    await page.locator('[data-tab="gen"]').click();
    assert.equal(await page.locator('#pdfFrame').isVisible(), false);
    assert.equal(await page.evaluate(() => pdfBlob), null);
    await page.setViewportSize({width: 390, height: 844});
    await page.locator('[data-tab="profile"]').click();
    await page.screenshot({path: path.join(output, 'mobile.png'), fullPage: true});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.deepEqual(errors, []);
    await writeFile(path.join(output, 'browser-result.json'), JSON.stringify({passed:true,model_calls:3,errors}, null, 2));
    console.log('Browser flow passed: invite -> import -> generate -> PDF preview -> download; mobile fits.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
