import { readFile } from 'node:fs/promises';
import { expect, test, type Locator, type Page } from '@playwright/test';

const base = '/quant-intel-platform';
const routes = [
  { name: 'English', path: `${base}/en/` },
  { name: 'Chinese', path: `${base}/?locale=zh-CN` },
];

async function rect(locator: Locator) {
  const box = await locator.boundingBox();
  expect(box, 'header control must have a visible rectangle').not.toBeNull();
  return box!;
}

function overlap(a: { x: number; y: number; width: number; height: number }, b: { x: number; y: number; width: number; height: number }) {
  return a.x < b.x + b.width && b.x < a.x + a.width
    && a.y < b.y + b.height && b.y < a.y + a.height;
}

async function chartColors(page: Page, selector: string) {
  const svg = page.locator(selector);
  await expect(svg, `expected report SVG at ${selector}`).toBeVisible();
  return svg.evaluate((node) => {
    const root = getComputedStyle(node);
    const background = node.querySelector('rect');
    const text = node.querySelector('text');
    if (!background || !text) throw new Error('report SVG is missing background or text');
    const probe = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    node.append(probe);
    probe.style.fill = root.getPropertyValue('--report-bg').trim();
    const expectedBg = getComputedStyle(probe).fill;
    probe.style.fill = root.getPropertyValue('--report-ink').trim();
    const expectedInk = getComputedStyle(probe).fill;
    probe.remove();
    return {
      bg: getComputedStyle(background).fill,
      ink: getComputedStyle(text).fill,
      expectedBg,
      expectedInk,
    };
  });
}

for (const width of [390, 768, 1280]) {
  for (const route of routes) {
    test(`${route.name} header and theme at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: 'light' });
      await page.goto(route.path);
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
      const brand = page.locator('.topbar .brand');
      const nav = page.locator('.topbar .top-nav');
      const links = nav.locator('a');
      const toggle = page.locator('#theme-toggle');
      await expect(links.first()).toBeVisible();
      await expect(toggle).toBeVisible();
      const controls = [brand, ...await links.all(), toggle];
      const boxes = await Promise.all(controls.map(rect));
      if (width >= 768) {
        for (const [index, box] of boxes.entries()) {
          expect(box.x, `header control ${index} stays in viewport at ${width}px`).toBeGreaterThanOrEqual(0);
          expect(box.x + box.width, `header control ${index} stays in viewport at ${width}px`).toBeLessThanOrEqual(width);
        }
      }
      for (let i = 0; i < boxes.length; i++) {
        for (let j = i + 1; j < boxes.length; j++) {
          expect(overlap(boxes[i], boxes[j]), `header controls ${i} and ${j} overlap at ${width}px`).toBe(false);
        }
      }
      for (let i = 1; i < await links.count(); i++) {
        const previous = await rect(links.nth(i - 1));
        const current = await rect(links.nth(i));
        if (Math.abs(previous.y - current.y) < 2) {
          expect(current.x - previous.x - previous.width, `navigation links ${i - 1}/${i} need 12px`).toBeGreaterThanOrEqual(12);
        }
      }
      // Every navigation target must remain reachable at phone width, including overflowed links.
      for (const link of await links.all()) {
        await link.scrollIntoViewIfNeeded();
        await expect(link).toBeInViewport();
      }
      await expect(toggle).toBeInViewport();
      if (route.name === 'Chinese') {
        for (const selector of ['#market-daily-chart svg', '#asia-daily-chart svg']) {
          const colors = await chartColors(page, selector);
          expect(colors.bg, `${selector} background follows light theme`).toBe(colors.expectedBg);
          expect(colors.ink, `${selector} text follows light theme`).toBe(colors.expectedInk);
        }
      }
      await toggle.click();
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
      await expect(toggle).toHaveAttribute('aria-pressed', 'true');
      await page.reload();
      await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
      await expect(toggle).toHaveAttribute('aria-pressed', 'true');
      if (route.name === 'Chinese') {
        for (const selector of ['#market-daily-chart svg', '#asia-daily-chart svg']) {
          const colors = await chartColors(page, selector);
          expect(colors.bg, `${selector} background follows dark theme`).toBe(colors.expectedBg);
          expect(colors.ink, `${selector} text follows dark theme`).toBe(colors.expectedInk);
        }
      }
    });
  }
}

test('Chinese PNG background matches the displayed Asia report', async ({ page }) => {
  await page.goto(`${base}/?locale=zh-CN`);
  await page.locator('#theme-toggle').click();
  const colors = await chartColors(page, '#asia-daily-chart svg');
  expect(colors.bg).toBe(colors.expectedBg);
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#download-asia-report').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/-asia-daily-report\.png$/);
  const bytes = await readFile(await download.path());
  const pixel = await page.evaluate(async (base64) => {
    const picture = new Image();
    picture.src = `data:image/png;base64,${base64}`;
    await picture.decode();
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('canvas unavailable');
    context.drawImage(picture, 0, 0);
    return Array.from(context.getImageData(0, 0, 1, 1).data);
  }, bytes.toString('base64'));
  const expected = await page.evaluate((color) => {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d')!;
    context.fillStyle = color;
    context.fillRect(0, 0, 1, 1);
    return Array.from(context.getImageData(0, 0, 1, 1).data);
  }, colors.bg);
  expect(pixel).toEqual(expected);
});

test('historical evening report loads with a visible graphic and resolved colors', async ({ page }) => {
  await page.goto(`${base}/reports/2026-09-28-evening/`);
  await expect(page.locator('.report-heading h1')).toBeVisible();
  const colors = await chartColors(page, '#asia-daily-chart svg');
  expect(colors.bg).toBe(colors.expectedBg);
  expect(colors.ink).toBe(colors.expectedInk);
});
