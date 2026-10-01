import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { startPreview } from './helpers/preview-server.mjs';
import { DEMO_PROFILE_SEED, PROFILE_STORAGE_KEY } from './helpers/demo-seed.mjs';
const server = await startPreview({ port: 5188 });
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:5188/');
  await page.evaluate(({ key, seed }) => localStorage.setItem(key, JSON.stringify(seed)), {
    key: PROFILE_STORAGE_KEY,
    seed: { ...DEMO_PROFILE_SEED, ownerId: 'family-browser-owner', dataMode: 'personal', preferredRole: 'elder' },
  });
  await page.reload();
  const nav = page.getByRole('navigation', { name: '主要导航' });
  await nav.getByRole('button', { name: '我的', exact: true }).click();
  await page.getByRole('button', { name: '允许共享', exact: true }).click();
  await page.getByRole('button', { name: '暂停共享', exact: true }).waitFor();
  await page.getByRole('button', { name: '生成家属邀请码', exact: true }).click();
  const code = await page.locator('.invite-code').innerText();
  await page.getByRole('button', { name: '切换身份', exact: true }).click();
  await page.getByRole('button', { name: /我是家属/ }).click();
  await page.getByPlaceholder('例如 AN-2026-K7QXW2RN9M').fill(code);
  await page.getByRole('button', { name: '绑定', exact: true }).click();
  await page.getByRole('heading', { name: /您好/ }).waitFor();
  const read = () =>
    page.evaluate(() => JSON.parse(localStorage.getItem('ankang-route1-family-state-v2:family-browser-owner')));
  assert.equal((await read()).familyLink.status, 'active');
  assert.equal((await read()).familySharing, 'granted');
  await page.getByRole('button', { name: /隐私设置.*数据共享/ }).click();
  await page.getByRole('button', { name: '暂停老人共享', exact: true }).click();
  assert.equal((await read()).familySharing, 'denied');
  await page.reload();
  await page.getByRole('button', { name: /隐私设置.*数据共享/ }).click();
  await page.getByRole('button', { name: '解除与老人端的绑定', exact: true }).click();
  await page.getByRole('heading', { name: '先完成家庭绑定', exact: true }).waitFor();
  assert.equal((await read()).familyLink, null);
  assert.deepEqual((await read()).sharedFindingIds, []);
  console.log('PASS React family/privacy: grant, bind, revoke, reload, unbind; owner-scoped storage');
} finally {
  await browser.close();
  server.stop();
}
