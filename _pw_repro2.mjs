import { chromium } from 'playwright';
import fs from 'fs';

const browser = await chromium.launch({ args: ['--no-sandbox'] });
const ctx = await browser.newContext();
const page = await ctx.newPage();

const events = [];
page.on('console', (msg) => events.push(`[console:${msg.type()}] ${msg.text()}`));
page.on('pageerror', (err) => events.push(`[pageerror] ${err.message}`));
page.on('requestfailed', (req) => events.push(`[requestfailed] ${req.method()} ${req.url()} - ${req.failure()?.errorText}`));
page.on('response', async (res) => {
  if (res.status() >= 400) {
    let body = '';
    try { body = (await res.text()).slice(0, 800); } catch {}
    events.push(`[http ${res.status()}] ${res.request().method()} ${res.url()} :: ${body}`);
  }
});

async function shot(name) {
  await page.screenshot({ path: `_pw_shots/${name}.png`, fullPage: true });
  console.log(`screenshot: ${name}`);
}
fs.mkdirSync('_pw_shots', { recursive: true });

const email = `repro2_${Date.now()}@example.com`;
const password = 'ReproTest123!';

try {
  console.log('=== SIGNUP ===');
  await page.goto('http://localhost:3000/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(1000);
  await page.click('button:has-text("Create Account")');
  await page.waitForTimeout(400);
  await page.fill('input[placeholder="Acme Trading Co."]', 'Repro Workspace 2');
  await page.fill('input[placeholder="Your name"]', 'Repro Tester Two');
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await page.click('button[type="submit"]:has-text("Create Account")');
  await page.waitForTimeout(4000);
  console.log('URL after signup:', page.url());
  await shot('10_dashboard');

  console.log('=== STRATEGY BUILDER: AI Generated mode ===');
  await page.goto('http://localhost:3000/strategies/new', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(2000);

  // Fill identifier + alpha thesis
  const thesis = 'When RSI(14) drops below 28 and price is above EMA(200), enter long. Exit when RSI exceeds 72.';
  await page.fill('textarea', thesis);
  // Identifier field
  const idInput = page.locator('input[placeholder="RSI_MeanRev_1D"]');
  if (await idInput.count()) await idInput.fill('Repro_RSI_Test');

  await shot('11_builder_filled');

  // Click Compile & Deploy
  const deployBtn = page.locator('button:has-text("Compile & Deploy Agent"), button:has-text("Compile")');
  console.log('deploy button count:', await deployBtn.count());
  await deployBtn.first().click();
  await page.waitForTimeout(8000);
  console.log('URL after deploy click:', page.url());
  await shot('12_after_deploy');

  console.log('=== events up to here ===');
  console.log(events.join('\n'));
  events.length = 0;

  // If we landed on a strategy detail page, try Run Agent
  if (/\/strategies\/[0-9a-f-]+/.test(page.url())) {
    console.log('=== STRATEGY DETAIL: Run Agent ===');
    await page.waitForTimeout(1500);
    await shot('13_strategy_detail');
    const runBtn = page.locator('button:has-text("Run Agent")');
    console.log('run button count:', await runBtn.count());
    if (await runBtn.count()) {
      await runBtn.first().click();
      await page.waitForTimeout(6000);
      await shot('14_after_run_click');
      // wait a bit more for ws logs to stream in
      await page.waitForTimeout(8000);
      await shot('15_execution_log');
    }
  } else {
    console.log('Did NOT land on strategy detail page — listing strategies page instead');
    await page.goto('http://localhost:3000/strategies', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(2000);
    await shot('13b_strategies_list');
  }

  console.log('=== final events ===');
  console.log(events.join('\n'));
} catch (e) {
  console.error('ERROR:', e);
  await shot('99_error');
} finally {
  await browser.close();
}
