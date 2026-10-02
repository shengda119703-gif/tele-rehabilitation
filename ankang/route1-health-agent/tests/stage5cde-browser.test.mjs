import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { startPreview } from './helpers/preview-server.mjs';
import { DEMO_PROFILE_SEED, PROFILE_STORAGE_KEY } from './helpers/demo-seed.mjs';
const require = createRequire(import.meta.url);
const { FamilyService } = require('../.test-build/src/family/FamilyService.js');
const { InMemoryFamilyPersistence } = require('../.test-build/src/family/FamilyPersistence.js');
const ownerId = 'stage5cde-owner',
  dataMode = 'personal';
const family = new FamilyService(ownerId, dataMode, new InMemoryFamilyPersistence());
family.confirmLinkRequest(family.generateInvite('2026-10-01'));
family.grant();
const server = await startPreview({ port: 5190 }),
  browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  // Browser acceptance only, no real notification, webhook, or remote transport.
  await page.route('https://**', (route) => route.abort());
  await page.addInitScript(() => {
    window.Notification = class {
      static permission = 'granted';
      static async requestPermission() {
        return 'granted';
      }
      constructor() {
        localStorage.setItem('test-push-count', String(Number(localStorage.getItem('test-push-count') ?? 0) + 1));
      }
      close() {}
    };
  });
  await page.goto('http://127.0.0.1:5190/');
  const seed = { ...DEMO_PROFILE_SEED, ownerId, dataMode, preferredRole: 'elder' };
  await page.evaluate(
    ({ key, seed, state }) => {
      localStorage.setItem(key, JSON.stringify(seed));
      localStorage.setItem('ankang-route1-family-state-v2:' + seed.ownerId, JSON.stringify(state));
    },
    { key: PROFILE_STORAGE_KEY, seed, state: family.readState() },
  );
  await page.reload();
  const nav = page.getByRole('navigation', { name: '主要导航' });
  await nav.getByRole('button', { name: '健康档案', exact: true }).click();
  await page.getByRole('button', { name: '＋ 上传新档案', exact: true }).click();
  await page
    .getByLabel('从文件选择')
    .setInputFiles({ name: 'report.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-test') });
  await page.getByRole('button', { name: '保存档案', exact: true }).click();
  await page.getByRole('button', { name: /report.pdf.*体检报告/ }).click();
  await page.getByRole('button', { name: '编辑档案', exact: true }).click();
  await page.getByLabel('档案名称').fill('edited report');
  await page.getByRole('button', { name: '保存档案', exact: true }).click();
  await page.getByRole('button', { name: /edited report.*体检报告/ }).waitFor();
  await page.reload();
  await nav.getByRole('button', { name: '健康档案', exact: true }).click();
  await page.getByRole('button', { name: /edited report.*体检报告/ }).click();
  assert.equal(await page.getByRole('link', { name: '下载原文件' }).getAttribute('download'), 'report.pdf');
  assert.equal(
    await page.getByRole('link', { name: '下载原文件' }).evaluate(async (a) => (await fetch(a.href)).text()),
    '%PDF-test',
  );
  // Switching stable owners with identical names must not reveal the attachment.
  await page.evaluate(
    ({ key, seed }) => localStorage.setItem(key, JSON.stringify({ ...seed, ownerId: 'different-owner' })),
    { key: PROFILE_STORAGE_KEY, seed },
  );
  await page.reload();
  await nav.getByRole('button', { name: '健康档案', exact: true }).click();
  await page.getByText('还没有档案，添加第一份资料吧。').waitFor();
  await page.evaluate(({ key, seed }) => localStorage.setItem(key, JSON.stringify(seed)), {
    key: PROFILE_STORAGE_KEY,
    seed,
  });
  await page.reload();
  await page.getByRole('button', { name: '打字聊天', exact: true }).click();
  await page.locator('#elder-chat input.chat-input').fill('我刚才在卫生间摔了一跤，现在胸口有点疼');
  await page.locator('#elder-chat button', { hasText: '发送' }).click();
  const ledgerKey = 'ankang-route1-notifications-v2:personal:' + ownerId;
  await page.waitForFunction((key) => {
    const rows = JSON.parse(localStorage.getItem(key) ?? '[]');
    return rows.length > 0 && rows.every((r) => r.phase === 'accepted');
  }, ledgerKey);
  const before = await page.evaluate(() => Number(localStorage.getItem('test-push-count')));
  await page.getByRole('button', { name: '返回首页', exact: true }).click();
  await nav.getByRole('button', { name: '我的', exact: true }).click();
  await page.getByRole('button', { name: '切换身份', exact: true }).click();
  await page.getByRole('button', { name: /我是家属/ }).click();
  await nav.getByRole('button', { name: '消息', exact: true }).click();
  await page
    .getByText(/已受理，送达未确认/)
    .first()
    .waitFor();
  await page.getByRole('button', { name: '我已知悉', exact: true }).first().click();
  assert.ok(
    (await page.evaluate((key) => JSON.parse(localStorage.getItem(key)), ledgerKey)).some(
      (r) => r.lifecycle === 'acknowledged' && r.phase === 'accepted',
    ),
  );
  await page.reload();
  await nav.getByRole('button', { name: '消息', exact: true }).click();
  await page
    .getByText(/已受理，送达未确认/)
    .first()
    .waitFor();
  assert.equal(await page.evaluate(() => Number(localStorage.getItem('test-push-count'))), before);
  assert.deepEqual(errors, []);
  console.log(
    'PASS Stage5CDE browser: attachment add/edit/read/reload/owner isolation, actual chat→notification acceptance→acknowledge→reload dedup; no real external delivery',
  );
} finally {
  await browser.close();
  server.stop();
}
