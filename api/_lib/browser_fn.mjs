// Runs INSIDE the hosted browser (Browserless /function API, Puppeteer). The server sends this file as `code`
// and the settings as `context`. It never types into forms, never pays, logs in or creates accounts: after
// every step a guard stops at payment, login or bot-check pages and hands the check to a person.
export default async function ({ page, context }) {
  const c = context;
  const started = Date.now();
  const out = { status: null, url: null, title: "", text: "", html: "", cart: null, shot: null, shotBefore: null, clicked: null,
                human_reason: null, error: null, out_of_time: false, notes: [] };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const forbidden = new RegExp(c.forbidden, "i");

  await page.setUserAgent(c.ua);
  await page.setViewport(c.viewport);
  await page.setRequestInterception(true);
  page.on("request", (req) => {
    const type = req.resourceType();
    if (type === "font" || type === "media" || (type === "image" && !c.wantShot)) return req.abort();
    return req.continue();
  });

  // Where are we? "payment" / "login" / "captcha" / null.
  const guard = () => page.evaluate(() => {
    const seen = (el) => {
      const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
      return r.width > 40 && r.height > 20 && s.visibility !== "hidden" && s.display !== "none";
    };
    const any = (sel) => [...document.querySelectorAll(sel)].some(seen);
    const path = location.pathname.toLowerCase();
    // Third-party one-click checkouts open as a big frame from their own site (phone + OTP, then payment).
    const big = (el) => { const r = el.getBoundingClientRect(); return seen(el) && r.width * r.height > innerWidth * innerHeight * 0.2; };
    const checkoutFrame = [...document.querySelectorAll("iframe")].some((f) => big(f) &&
      /gokwik|shiprocket|fastrr|razorpay|simpl|cashfree|juspay|paytm|phonepe|snapmint|zecpe|breeze|checkout|payment/i.test(f.src || f.id || f.name || ""));
    if (/\/checkouts?(\/|$)|\/payments?(\/|$)/.test(path) || checkoutFrame ||
        any('input[autocomplete^="cc-"], iframe[src*="card-fields"], iframe[src*="shopifycs"], iframe[src*="stripe"]')) return "payment";
    if (/\/account\/login|\/login|\/signin|\/sign-in/.test(path) || any("input[type=password]") ||
        any('input[autocomplete="one-time-code"], input[name*="otp" i], input[id*="otp" i]')) return "login";
    if (/just a moment|attention required|verify you are human/i.test(document.title) ||
        any('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="challenges.cloudflare"]')) return "captcha";
    return null;
  });

  // Close marketing pop-ups the way a shopper would (their close button), or hide them. Never fills them in.
  const closePopups = () => page.evaluate(() => {
    let closed = 0;
    const W = innerWidth, H = innerHeight;
    const isPopup = (el) => /popup|modal|overlay|newsletter|klaviyo|privy|poppro|spin|wheel|cookie|consent|subscribe/i
      .test(`${el.id} ${el.className}`) && !/cart|drawer|menu|header|search|checkout|gokwik|shiprocket|razorpay/i.test(`${el.id} ${el.className}`) &&
      !el.querySelector("iframe");  // a pop-up holding a frame may be a checkout: leave it for the guard
    for (const el of document.querySelectorAll("body *")) {
      const s = getComputedStyle(el);
      if (s.position !== "fixed" || s.display === "none" || s.visibility === "hidden" || !isPopup(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.width * r.height < W * H * 0.15) continue;
      const btn = el.querySelector('[aria-label*="close" i], [class*="close" i], [title*="close" i]');
      if (btn) btn.click(); else el.style.setProperty("display", "none", "important");
      closed += 1;
    }
    return closed;
  });

  // The visible element a shopper would press for "text=Sand" or "css=button[name=add]".
  const target = async (spec) => {
    if (spec.startsWith("css=")) {
      const handles = await page.$$(spec.slice(4));
      for (const h of handles) if (await h.evaluate((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })) return h;
      return null;
    }
    const want = spec.replace(/^text=/, "").trim().toLowerCase();
    const handle = await page.evaluateHandle((want) => {
      const seen = (el) => {
        const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
      };
      const name = (el) => (el.innerText || el.value || el.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").toLowerCase();
      const all = [...document.querySelectorAll("button, a, label, summary, [role=button], input[type=submit], input[type=button]")].filter(seen);
      return all.find((el) => name(el) === want) || all.find((el) => name(el).includes(want)) || null;
    }, want);
    return handle.asElement();
  };

  // Frame the picture for a clicked element: scroll so the nearest block around it that holds an image/video (and
  // fits the screen) starts just under any sticky header, keeping the element itself in view. Returns where it ended up.
  const frame = (el) => el.evaluate((e) => {
    const vh = innerHeight;
    const abs = (n) => { const r = n.getBoundingClientRect(); return { top: r.top + scrollY, bottom: r.bottom + scrollY, h: r.height }; };
    let head = 0;
    for (const n of document.querySelectorAll("header, nav, [class*=header i], [id*=header i], [class*=sticky i]")) {
      const s = getComputedStyle(n); const r = n.getBoundingClientRect();
      if ((s.position === "fixed" || s.position === "sticky") && r.top <= 4 && r.bottom > 0 && r.width > innerWidth * 0.5 && r.height < vh * 0.3) head = Math.max(head, r.bottom);
    }
    head = head > 0 ? head + 8 : 100;
    const hasMedia = (n) => [...n.querySelectorAll("img, picture, video, canvas")].some((m) => { const r = m.getBoundingClientRect(); return r.width > 60 && r.height > 60; });
    let ctx = e;
    for (let n = e.parentElement; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
      if (hasMedia(n)) { if (abs(n).h <= vh - head) ctx = n; break; }
    }
    const el = abs(e), box = abs(ctx);
    let y = box.top - head;
    y = Math.min(y, el.top - head);          // the element stays below the header
    y = Math.max(y, el.bottom - vh + 12);    // and above the bottom edge
    y = Math.max(0, Math.min(y, document.documentElement.scrollHeight - vh));
    window.scrollTo({ top: y, behavior: "instant" });
    e.setAttribute("data-ec-target", "1");
    return { y: scrollY, top: el.top };
  });
  // Frame it again for the after picture: same scroll as before unless the element moved (or the page changed).
  const reframe = async (before, urlBefore) => {
    const found = await page.$("[data-ec-target]");
    if (!found) { if (page.url() === urlBefore) await page.evaluate((y) => window.scrollTo({ top: y, behavior: "instant" }), before.y); return; }
    const now = await found.evaluate((e) => e.getBoundingClientRect().top + scrollY);
    if (Math.abs(now - before.top) > 20) await frame(found);
    else await page.evaluate((y) => window.scrollTo({ top: y, behavior: "instant" }), before.y);
  };

  const steps = c.steps.length && c.steps[0].goto !== undefined ? c.steps : [{ goto: c.start }, ...c.steps];
  let lastClick = -1;  // the click being judged: a "before" picture is taken just ahead of it
  steps.forEach((st, i) => { if (st.click) lastClick = i; });
  let framed = null, urlBefore = null;
  try {
    for (const [i, step] of steps.entries()) {
      if (Date.now() - started > c.budgetMs) { out.out_of_time = true; break; }
      if (step.goto !== undefined) {
        const resp = await page.goto(c.base + step.goto, { waitUntil: "domcontentloaded", timeout: 20000 });
        if (out.status === null) out.status = resp ? resp.status() : null;
        await sleep(1800);
        out.notes.push(`opened ${step.goto}`);
      } else if (step.click) {
        await page.keyboard.press("Escape").catch(() => {});
        if (await closePopups()) out.notes.push("closed a pop-up");
        const el = await target(step.click);
        const label = step.click.replace(/^(text|css)=/, "");
        if (!el) {
          if (step.optional) { out.notes.push(`no "${label}" here, skipped`); continue; }
          out.error = `We couldn't find "${label}" to click on the page.`;
          break;
        }
        const name = await el.evaluate((e) => (e.innerText || e.value || e.getAttribute("aria-label") || "").trim());
        if (forbidden.test(name)) { out.human_reason = `forbidden:${name.slice(0, 40)}`; break; }
        if (i === lastClick && c.wantShot && Date.now() - started < c.budgetMs - 10000) {
          framed = await frame(el);
          urlBefore = page.url();
          if (await guard()) { out.human_reason = await guard(); break; }
          await sleep(400);  // lazy images
          out.shotBefore = await page.screenshot({ type: "jpeg", quality: 55, encoding: "base64" });
          out.clicked = label.slice(0, 80);
        } else {
          await el.evaluate((e) => e.scrollIntoView({ block: "center" }));
        }
        // If the click opens a new page (e.g. "Check out"), wait for it to load before the guard looks.
        let navigating = false;
        const onRequest = (r) => { if (r.isNavigationRequest() && r.frame() === page.mainFrame()) navigating = true; };
        page.on("request", onRequest);
        const loaded = page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 12000 }).catch(() => null);
        await el.click();
        await sleep(Math.min(step.wait_ms || 1800, 5000));
        if (navigating) { await loaded; await sleep(1500); }
        page.off("request", onRequest);
        // Some clicks open a slow pop-up (e.g. a one-click checkout) instead of a page: look twice.
        if (!navigating && !(await guard())) await sleep(2500);
        out.notes.push(`clicked ${label}`);
      } else if (step.wait) {
        await sleep(Math.min(Number(step.wait) * 1000, 5000));
      } else if (step.scroll) {
        await page.evaluate((y) => window.scrollTo(0, y === "bottom" ? document.body.scrollHeight : Number(y) || 0), step.scroll);
        await sleep(600);
      }
      const where = await guard();
      if (where) { out.human_reason = where; break; }
    }
    out.url = page.url();
    out.title = await page.title();
    if (!out.human_reason && !out.error && !out.out_of_time) {
      out.text = (await page.evaluate(() => (document.body ? document.body.innerText : ""))).slice(0, 20000);
      if (c.wantHtml) out.html = (await page.content()).slice(0, 300000);
      if (c.wantCart) {
        out.cart = await page.evaluate(() => fetch("/cart.js", { headers: { Accept: "application/json" } })
          .then((r) => r.json()).catch(() => null));
      }
      if (c.wantShot) {
        if (await closePopups()) out.notes.push("closed a pop-up");
        if (framed) {
          await reframe(framed, urlBefore);
          const where = await guard();
          if (where) { out.human_reason = where; out.shotBefore = null; out.clicked = null; return { data: out, type: "application/json" }; }
          await sleep(400);
        }
        await sleep(300);
        out.shot = await page.screenshot({ type: "jpeg", quality: 55, encoding: "base64" });
      }
    }
  } catch (e) {
    out.error = `The page didn't work in the browser: ${String((e && e.message) || e).slice(0, 160)}`;
    out.url = page.url();
  }
  return { data: out, type: "application/json" };
}
