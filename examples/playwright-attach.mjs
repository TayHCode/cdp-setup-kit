import { chromium } from 'playwright';

const browser = await chromium.connectOverCDP('http://127.0.0.1:9333');
try {
  const context = browser.contexts()[0];
  const page = context.pages()[0] || await context.newPage();
  await page.goto('https://example.com');
  console.log(await page.title());
} finally {
  // For an attached browser, this disconnects and leaves the window open.
  await browser.close();
}
