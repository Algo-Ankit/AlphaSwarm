import { chromium } from 'playwright';
import fs from 'fs';

const browser = await chromium.launch({ args: ['--no-sandbox'] });
const ctx = await browser.newContext();
const page = await ctx.newPage();

const consoleMsgs = [];
page.on('console', (msg) => consoleMsgs.push(`[${msg.type()}] ${msg.text()}`));
page.on('pageerror', (err) => consoleMsgs.push(`[pageerror] ${err.message}`));
page.on('requestfailed', (req) => consoleMsgs.push(`[requestfailed] ${req.method()} ${req.url()} - ${req.failure()?.errorText}`));
page.on('response', async (res) => {
  if (res.status() >= 400) {
    let body = '';
    try { body = (await res.text()).slice(0, 500); } catch {}
    consoleMsgs.push(`[http ${res.status()}] ${res.url()} :: ${body}`);
  }
});

async function shot(name) {
  await page.screenshot({ path: `_pw_shots/${name}.png`, fullPage: true });
  console.log(`screenshot: ${name}`);
}
fs.mkdirSync('_pw_shots', { recursive: true });

const email = `repro_${Date.now()}@example.com`;
const password = 'ReproTest123!';

try {
  console.log('--- nav to login ---');
  await page.goto('http://localhost:3000/login', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(1500);

  console.log('--- create account ---');
  await page.click('button:has-text("Create Account")');
  await page.waitForTimeout(500);
  await page.fill('input[placeholder="Acme Trading Co."]', 'Repro Workspace');
  await page.fill('input[placeholder="Your name"]', 'Repro Tester');
  await page.fill('input[type="email"]', email);
  await page.fill('input[type="password"]', password);
  await shot('00_signup_form');
  await page.click('button[type="submit"]:has-text("Create Account")');
  await page.waitForTimeout(5000);
  await shot('01_after_signup');
  console.log('URL after signup:', page.url());

  console.log('--- nav to strategies/new ---');
  await page.goto('http://localhost:3000/strategies/new', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(2500);
  await shot('02_new_strategy');
  console.log('URL:', page.url());

  fs.writeFileSync('_pw_shots/02_new_strategy.html', await page.content());

  console.log('--- console/network log so far ---');
  console.log(consoleMsgs.join('\n'));
  consoleMsgs.length = 0;
} catch (e) {
  console.error('ERROR:', e);
} finally {
  await browser.close();
}
