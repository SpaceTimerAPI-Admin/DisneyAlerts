import { chromium } from 'playwright';
import fs from 'fs/promises';
import path from 'path';
import { DISNEY_EMAIL, DISNEY_PASSWORD } from './config.js';

const COOKIE_PATH = path.join(process.cwd(), 'session', 'cookies.json');

export async function getCookies() {
  try {
    const cookiesData = await fs.readFile(COOKIE_PATH, 'utf-8');
    return JSON.parse(cookiesData);
  } catch {
    const browser = await chromium.launch({ args: ['--no-sandbox'] });
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto('https://disneyworld.disney.go.com/');
    await page.click('text=Sign In');
    await page.fill('#login-email-input', DISNEY_EMAIL);
    await page.fill('#login-password-input', DISNEY_PASSWORD);
    await page.click('button[type=submit]');
    await page.waitForURL('**/profile', { timeout: 60000 });
    const cookies = await context.cookies();
    await fs.mkdir(path.dirname(COOKIE_PATH), { recursive: true });
    await fs.writeFile(COOKIE_PATH, JSON.stringify(cookies, null, 2));
    await browser.close();
    return cookies;
  }
}
