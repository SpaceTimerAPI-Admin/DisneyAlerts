import { chromium } from 'playwright';
import fs from 'fs';

const COOKIE_PATH = './session/cookies.json';

export async function loginDisney() {
  if (fs.existsSync(COOKIE_PATH)) {
    const stats = fs.statSync(COOKIE_PATH);
    if (Date.now() - stats.mtimeMs < 1000 * 60 * 50) {
      console.log('✅ Reusing Disney cookies');
      return;
    }
  }
  console.log('🔐 Logging into Disney...');
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('https://disneyworld.disney.go.com/signin/');
  await page.fill('#username', process.env.DISNEY_EMAIL);
  await page.fill('#password', process.env.DISNEY_PASSWORD);
  await page.click('button[type=submit]');
  await page.waitForURL('https://disneyworld.disney.go.com/dine-res/');
  const cookies = await page.context().cookies();
  fs.mkdirSync('./session', { recursive: true });
  fs.writeFileSync(COOKIE_PATH, JSON.stringify(cookies, null, 2));
  await browser.close();
  console.log('✅ Disney cookies refreshed');
}