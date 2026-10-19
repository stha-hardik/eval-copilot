// Temporary M7 harness: runs api/_lib/browser_fn.mjs with a local Chrome the way Browserless /function does.
import puppeteer from "puppeteer";
import fs from "fs";
import fn from "../../api/_lib/browser_fn.mjs";

const PHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";
const LAPTOP_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";
const FORBIDDEN = String.raw`\b(pay|pay now|place order|complete order|confirm order|submit order|buy it now|buy now|log ?in|sign ?in|sign ?up|register|create account|subscribe|unlock|spin)\b`;
const VP = { phone: { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 1 },
             laptop: { width: 1440, height: 900, deviceScaleFactor: 1 } };
const P = "/products/solaris";
const cases = [
  ["p1-menu", "phone", "/", [{ click: "css=summary[aria-label=Menu]", optional: true }], true, false],
  ["p1-menu", "laptop", "/", [{ click: "css=summary[aria-label=Menu]", optional: true }], true, false],
  ["p6-sand", "phone", P, [{ goto: P }, { click: "text=Sand" }], true, false],
  ["p6-sand", "laptop", P, [{ goto: P }, { click: "text=Sand" }], true, false],
  ["p7-turnon", "laptop", P, [{ goto: P }, { click: "text=Turn On" }], true, false],
  ["p8-add", "phone", P, [{ goto: P }, { click: "css=button[name=add]" }], true, true],
  ["p8-add", "laptop", P, [{ goto: P }, { click: "css=button[name=add]" }], true, true],
  ["p10-checkout", "laptop", P, [{ goto: P }, { click: "css=button[name=add]" }, { goto: "/cart" }, { click: "css=button[name=checkout]" }], true, true],
  ["forbidden", "laptop", P, [{ goto: P }, { click: "text=Buy it now" }], false, false],
];
fs.mkdirSync("shots", { recursive: true });
const browser = await puppeteer.launch({ args: ["--no-sandbox"] });
for (const [name, device, start, steps, wantShot, wantCart] of cases) {
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  const t = Date.now();
  const { data } = await fn({ page, context: { base: "https://bublsolar.com", start, steps, ua: device === "phone" ? PHONE_UA : LAPTOP_UA,
    viewport: VP[device], wantShot, wantCart, wantHtml: false, forbidden: FORBIDDEN, budgetMs: 37000 } });
  if (data.shot) fs.writeFileSync(`shots/${name}-${device}.jpg`, Buffer.from(data.shot, "base64"));
  console.log(JSON.stringify({ case: name, device, secs: Math.round((Date.now() - t) / 1000), status: data.status, url: data.url,
    notes: data.notes, human_reason: data.human_reason, error: data.error, out_of_time: data.out_of_time,
    cart: data.cart && { item_count: data.cart.item_count, items: data.cart.items.map((i) => [i.product_title, i.variant_title, i.quantity]) },
    shot_kb: data.shot ? Math.round(data.shot.length * 0.75 / 1024) : 0, text_len: data.text.length }));
  await ctx.close();
}
await browser.close();

// Diagnostic: what does "Check out" on bublsolar.com really open?
{
  const b = await puppeteer.launch({ args: ["--no-sandbox"] });
  const page = await b.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  const hosts = new Set();
  page.on("request", (r) => { try { hosts.add(new URL(r.url()).hostname); } catch (e) {} });
  await page.goto("https://bublsolar.com/products/solaris", { waitUntil: "domcontentloaded" });
  await new Promise((r) => setTimeout(r, 2500));
  await page.evaluate(() => document.querySelector("button[name=add]").click());
  await new Promise((r) => setTimeout(r, 2500));
  await page.goto("https://bublsolar.com/cart", { waitUntil: "domcontentloaded" });
  await new Promise((r) => setTimeout(r, 2500));
  const before = new Set(hosts);
  const btn = await page.$("button[name=checkout]");
  console.log("checkout button html:", await btn.evaluate((e) => e.outerHTML.slice(0, 300)));
  await btn.click();
  await new Promise((r) => setTimeout(r, 7000));
  console.log("DIAG url after click:", page.url());
  console.log("DIAG new hosts:", [...hosts].filter((h) => !before.has(h)).join(", "));
  console.log("DIAG iframes:", JSON.stringify(await page.evaluate(() => [...document.querySelectorAll("iframe")].map((f) => {
    const r = f.getBoundingClientRect(); return [f.src.slice(0, 90), f.id, Math.round(r.width), Math.round(r.height)]; }).filter((x) => x[2] > 50))));
  console.log("DIAG big fixed:", JSON.stringify(await page.evaluate(() => [...document.querySelectorAll("body *")].filter((el) => {
    const s = getComputedStyle(el); const r = el.getBoundingClientRect();
    return s.position === "fixed" && s.display !== "none" && r.width * r.height > innerWidth * innerHeight * 0.3; })
    .map((el) => `${el.tagName}#${el.id}.${String(el.className).slice(0, 60)}`).slice(0, 8))));
  await page.screenshot({ path: "shots/diag-after-checkout.jpg", type: "jpeg", quality: 55 });
  await b.close();
}
