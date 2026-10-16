// Phone-like smoothness measurement for any page.
// Usage: node fps.mjs <url> [cpuRate=4] [scroll=1|0] [--still]
//   cpuRate  2 ≈ mid-range phone, 4 ≈ low-end phone
//   scroll   1 = scroll the page during the measurement, 0 = idle
//   --still  emulate prefers-reduced-motion (compare: is it the animations?)
// Needs `playwright` resolvable from the current directory (npm i playwright).
import { chromium } from 'playwright';

const args = process.argv.slice(2);
const still = args.includes('--still');
const [url, rate = '4', scroll = '1'] = args.filter((a) => a !== '--still');
if (!url) {
  console.error('usage: node fps.mjs <url> [cpuRate=4] [scroll=1|0] [--still]');
  process.exit(1);
}

const browser = await chromium.launch();
const ctx = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2.6,
  reducedMotion: still ? 'reduce' : 'no-preference',
});
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));

await page.goto(url, { waitUntil: 'load' });
await page.waitForTimeout(3000); // let lazy players/images settle

const cdp = await ctx.newCDPSession(page);
await cdp.send('Emulation.setCPUThrottlingRate', { rate: Number(rate) });
await page.waitForTimeout(800);

const result = await page.evaluate(
  (doScroll) =>
    new Promise((resolve) => {
      let frames = 0;
      let long = 0;
      let mutations = 0;
      const mo = new MutationObserver((list) => (mutations += list.length));
      mo.observe(document.body, { subtree: true, attributes: true, childList: true });
      const max = document.documentElement.scrollHeight - innerHeight;
      let y = 0;
      let last = performance.now();
      const t0 = last;
      const step = (t) => {
        frames++;
        if (t - last > 50) long++;
        last = t;
        if (doScroll && max > 0) {
          y += 4;
          scrollTo(0, y % max);
        }
        if (t - t0 < 4000) requestAnimationFrame(step);
        else {
          mo.disconnect();
          resolve({
            uiFps: Math.round(frames / ((t - t0) / 1000)),
            longFrames: long,
            domMutationsPerSec: Math.round(mutations / 4),
            runningAnimations: document.getAnimations().length,
            svgElements: document.querySelectorAll('svg *').length,
          });
        }
      };
      requestAnimationFrame(step);
    }),
  scroll === '1',
);

const resources = await page.evaluate(() =>
  performance
    .getEntriesByType('resource')
    .map((r) => ({ name: r.name.split('/').pop().split('?')[0], kb: Math.round(r.transferSize / 1024) }))
    .sort((a, b) => b.kb - a.kb)
    .slice(0, 8),
);

console.log(
  JSON.stringify({ url, cpuRate: Number(rate), scroll: scroll === '1', still, ...result, heaviestTransfers: resources, errors }, null, 2),
);
await browser.close();
