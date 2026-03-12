import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://localhost:5174/system', { waitUntil: 'networkidle', timeout: 15000 });
  await new Promise(r => setTimeout(r, 2000));

  const qs = page.locator('button:has-text("Quick Start")').first();
  await qs.click();
  await new Promise(r => setTimeout(r, 1500));

  // Get the full HTML of the Quick Start section area
  const html = await page.evaluate(() => {
    // Look for anything after "Quick Start" text
    const body = document.body.innerHTML;
    const idx = body.indexOf('Quick Start');
    return body.slice(Math.max(0, idx - 200), idx + 2000);
  });
  console.log(html.slice(0, 3000));

  await browser.close();
})();
