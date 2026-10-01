import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import { startPreview } from './helpers/preview-server.mjs';
import { DEMO_PROFILE_SEED, PROFILE_STORAGE_KEY } from './helpers/demo-seed.mjs';

const server = await startPreview({ port: 5186 });
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:5186/');
  await page.evaluate(({ key, profile }) => localStorage.setItem(key, JSON.stringify(profile)), {
    key: PROFILE_STORAGE_KEY,
    profile: { ...DEMO_PROFILE_SEED, dataMode: 'personal', preferredRole: 'elder' },
  });
  await page.reload();
  const nav = page.getByRole('navigation', { name: '主要导航' });
  await nav.getByRole('button', { name: '药物', exact: true }).click();
  await page.getByRole('button', { name: '＋ 添加药物' }).click();
  await page.getByLabel('药物名称', { exact: true }).fill('测试药物甲');
  await page.getByLabel('每次剂量', { exact: false }).fill('1 片');
  await page.getByLabel('用途 / 医嘱说明').fill('按医嘱记录');
  await page.getByLabel('服用时间', { exact: false }).fill('08:00');
  await page.getByRole('button', { name: '保存药物' }).click();
  await page.getByRole('heading', { name: '测试药物甲', exact: true }).waitFor();
  const read = () => page.evaluate((key) => JSON.parse(localStorage.getItem(key)), PROFILE_STORAGE_KEY);
  const first = await read();
  const id = first.profile.medicationRecords.find((m) => m.name === '测试药物甲').id;
  for (const status of ['stopped', 'active']) {
    await page.getByRole('button', { name: '编辑', exact: true }).click();
    await page.getByLabel('药物名称', { exact: true }).fill('测试药物乙');
    await page.getByLabel('使用状态').selectOption(status);
    await page.getByRole('button', { name: '保存药物' }).click();
    await page.getByRole('heading', { name: '测试药物乙', exact: true }).waitFor();
    const stored = await read();
    const record = stored.profile.medicationRecords.find((m) => m.id === id);
    assert.deepEqual(record, { id, name: '测试药物乙', dose: '1 片', purpose: '按医嘱记录', times: '08:00', status });
    assert.equal(stored.profile.medications.includes('测试药物乙'), status === 'active');
  }
  await page.reload();
  await nav.getByRole('button', { name: '药物', exact: true }).click();
  await page.getByRole('button', { name: /测试药物乙/ }).click();
  assert.equal((await read()).ownerId, first.ownerId);
  const beforeFailure = await read();
  await page.getByRole('button', { name: '编辑', exact: true }).click();
  await page.getByLabel('药物名称', { exact: true }).fill('不应保存');
  await page.evaluate((key) => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (name, value) {
      if (name === key) throw new Error('test quota exceeded');
      return original.call(this, name, value);
    };
  }, PROFILE_STORAGE_KEY);
  await page.getByRole('button', { name: '保存药物' }).click();
  await page.getByRole('alert').filter({ hasText: '保存失败' }).waitFor();
  assert.equal(await page.getByLabel('药物名称', { exact: true }).inputValue(), '不应保存');
  assert.deepEqual(await read(), beforeFailure);
  console.log(
    'PASS medication UI: add/edit/stop/resume, fields, stable IDs after reload, failed save retains draft/data',
  );
} finally {
  await browser.close();
  server.stop();
}
