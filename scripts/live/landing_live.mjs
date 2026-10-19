// Temporary: checks the public landing page and the login routing on the live site, as a logged-out visitor
// and as a brand-new account. Runs on a GitHub runner (open internet). The password is random and never written down.
import { chromium } from "playwright";
import crypto from "crypto";
import fs from "fs";

const BASE = process.env.BASE || "https://eval-copilot.vercel.app";
const results = [];
let failed = 0;
function check(name, ok, detail) {
  results.push({ name, ok: !!ok, detail: detail || "" });
  if (!ok) failed++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  · " + detail : ""}`);
}
const path = (page) => new URL(page.url()).pathname + new URL(page.url()).search;
const visible = async (page, name) => page.getByRole("link", { name, exact: true }).first().isVisible().catch(() => false);

fs.mkdirSync("shots", { recursive: true });
const browser = await chromium.launch();

for (const [device, viewport] of [["laptop", { width: 1280, height: 800 }], ["phone", { width: 390, height: 844 }]]) {
  for (const theme of ["light", "dark"]) {
    const ctx = await browser.newContext({ viewport, colorScheme: theme, isMobile: device === "phone", hasTouch: device === "phone" });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    const tag = `${device}-${theme}`;

    // 1. Logged out: "/" is the landing page with Log in and Sign up.
    await page.goto(BASE + "/", { waitUntil: "networkidle" });
    check(`${tag}: landing headline`, await page.getByText("Test whether your app really works the way you think it does.").first().isVisible());
    check(`${tag}: logged out shows Log in + Sign up`, (await visible(page, "Log in")) && (await visible(page, "Sign up")));
    check(`${tag}: logged out hides Dashboard`, !(await visible(page, "Dashboard")));
    const width = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    check(`${tag}: no sideways scroll`, width[0] <= width[1], `page ${width[0]} / viewport ${width[1]}`);
    await page.screenshot({ path: `shots/landing-${tag}-top.png` });
    await page.screenshot({ path: `shots/landing-${tag}-full.png`, fullPage: true });

    if (theme === "light") {
      // 2. "Test yours" goes to sign up (with a way to log in).
      await page.getByRole("link", { name: /Test yours/ }).first().click();
      await page.waitForLoadState("networkidle");
      check(`${tag}: Test yours → /signup`, path(page).startsWith("/signup"), path(page));
      check(`${tag}: sign up page links to log in`, await page.getByText(/log in/i).first().isVisible());
      await page.screenshot({ path: `shots/signup-${tag}.png` });

      // 3. A protected page sends a logged-out visitor to /login and remembers where they were.
      await page.goto(BASE + "/home.html", { waitUntil: "networkidle" });
      check(`${tag}: projects page → /login?next=`, path(page).startsWith("/login?next=%2Fhome.html"), path(page));
      await page.screenshot({ path: `shots/login-${tag}.png` });
    }
    check(`${tag}: no script errors`, errors.length === 0, errors.join(" | "));
    await ctx.close();
  }
}

// 4. Sign up a brand-new test account (laptop, then the same flow on a phone with another account).
for (const [device, viewport] of [["laptop", { width: 1280, height: 800 }], ["phone", { width: 390, height: 844 }]]) {
  const ctx = await browser.newContext({ viewport, isMobile: device === "phone", hasTouch: device === "phone" });
  const page = await ctx.newPage();
  const email = `landing.test+${Date.now()}${device}@example.com`;
  const password = crypto.randomBytes(18).toString("base64url");
  await page.goto(BASE + "/signup", { waitUntil: "networkidle" });
  await page.locator('input[type="email"]').first().fill(email);
  await page.locator('input[type="password"]').first().fill(password);
  await page.locator('form button[type="submit"]').first().click();
  await page.waitForURL((u) => !u.pathname.startsWith("/signup"), { timeout: 20000 }).catch(() => {});
  await page.waitForLoadState("networkidle");
  check(`${device}: after sign up → landing page`, path(page) === "/", path(page));
  check(`${device}: logged in shows Dashboard`, await visible(page, "Dashboard"));
  check(`${device}: logged in hides Log in / Sign up`, !(await visible(page, "Log in")) && !(await visible(page, "Sign up")));
  await page.screenshot({ path: `shots/landing-${device}-loggedin.png` });

  // "Test yours" when logged in → dashboard.
  await page.getByRole("link", { name: /Test yours/ }).first().click();
  await page.waitForLoadState("networkidle");
  check(`${device}: logged in Test yours → projects`, path(page).startsWith("/home.html"), path(page));
  await page.goto(BASE + "/", { waitUntil: "networkidle" });

  await page.getByRole("link", { name: "Dashboard", exact: true }).first().click();
  await page.waitForLoadState("networkidle");
  check(`${device}: Dashboard → projects page`, path(page).startsWith("/home.html"), path(page));
  await page.screenshot({ path: `shots/home-${device}-light.png` });

  // Theme switch in the avatar menu, between "Signed in as" and "Log out".
  await page.locator("#account-menu summary, #account-menu button, .avatar").first().click().catch(() => {});
  const order = await page.evaluate(() => {
    const menu = document.getElementById("account-menu");
    if (!menu) return null;
    const text = menu.innerText;
    return [text.search(/signed in as/i), text.search(/dark|light|theme/i), text.search(/log out/i)];  // innerText follows CSS capitals
  });
  check(`${device}: theme switch sits between Signed in as and Log out`, order && order[0] >= 0 && order[0] < order[1] && order[1] < order[2], JSON.stringify(order));
  const before = await page.evaluate(() => document.documentElement.dataset.theme);
  await page.locator("#account-menu").getByRole("button", { name: /dark|light|theme/i }).first().click()
    .catch(() => page.locator("#account-menu").getByRole("switch").first().click());
  const after = await page.evaluate(() => document.documentElement.dataset.theme);
  check(`${device}: theme switch changes the theme`, before !== after, `${before} → ${after}`);
  await page.reload({ waitUntil: "networkidle" });
  check(`${device}: theme choice kept after reload`, (await page.evaluate(() => document.documentElement.dataset.theme)) === after);
  await page.keyboard.press("Escape");
  await page.screenshot({ path: `shots/home-${device}-${after}.png` });

  // Log out → landing shows Log in / Sign up again.
  await page.locator("#account-menu summary, #account-menu button, .avatar").first().click().catch(() => {});
  await page.locator("#menu-logout").click();
  await page.waitForLoadState("networkidle");
  check(`${device}: log out → landing`, path(page) === "/", path(page));
  check(`${device}: logged out again shows Log in + Sign up`, (await visible(page, "Log in")) && (await visible(page, "Sign up")));

  // Log back in through /login?next= → returns to the page you asked for.
  await page.goto(BASE + "/home.html", { waitUntil: "networkidle" });
  await page.locator('input[type="email"]').first().fill(email);
  await page.locator('input[type="password"]').first().fill(password);
  await page.locator('form button[type="submit"]').first().click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20000 }).catch(() => {});
  check(`${device}: log in from a protected page → back to it`, path(page).startsWith("/home.html"), path(page));
  await ctx.close();
}

await browser.close();
fs.writeFileSync("shots/results.json", JSON.stringify(results, null, 2));
console.log(failed ? `RESULT: FAIL (${failed} failed)` : `RESULT: PASS (${results.length} checks)`);
process.exit(failed ? 1 : 0);
