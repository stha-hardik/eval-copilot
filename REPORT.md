# Eval Co-pilot: final report

- **Live app:** https://eval-copilot.vercel.app
- **Code:** https://github.com/stha-hardik/eval-copilot (public, branch `main`; every push deploys)
- **Health check:** https://eval-copilot.vercel.app/api/health → `{"ok":true}`

Eval Co-pilot takes up to 10 golden pairs (what a shopper does + what a good result has), tries each one on
the live site as a phone and as a laptop, marks every row pass / fail / can't test with a one-line reason,
picks the worst fails, and keeps every run so Run 1 sits next to Run 2.

## What works, per milestone, and how it was tested

| Milestone | What works | How it was tested |
|---|---|---|
| **M1** Skeleton, database, deploy | 8 tables with Row Level Security in Supabase; Vercel project with the 3 settings (Supabase link, Supabase public key, Groq key); public link (Vercel login wall turned off); `/api/health` | Supabase connector + security advisor; `/api/health` live → ok; every page and stylesheet → 200 |
| **M2** Login, projects, privacy | Sign up, log in, log out, create and list projects; each builder sees only their own | Two-user test twice: in the database (16 steps, all passed) and through the live app (B sees 0 projects and gets 404 for A's project). See `TESTING.md` |
| **M3** Golden pairs + Brajesh's data | Add / edit / approve / priority, example pair, mic (browser speech), Tidy with AI, Suggest pairs; "Bubl Solar" with the 10 pairs, all approved, #8 priority, real handles read from bublsolar.com | Seed script through the app's own doors; every AI-proposed check compared with the live pages; 4 bad checks fixed before Run 1 |
| **M4** Run | Run all, phone + laptop, code checks, AI checks and one-line whys, "Looks right / Looks wrong" for human checks, worst fails with the AI's advice, table fills in live | Run 1 by script; Run 3 through the real screens in Chrome |
| **M5** Re-run changed + compare | Tick boxes, "Other changes" box → AI turns it into a check to approve, "Good now? yes / no" per pair, compare with any earlier run (FIXED / BROKE / same), old runs never change | Run 2 by script; Run 4 through the real screens; Run 1's rows checked unchanged after every re-run |
| **M6** Polish + docs | Your "Tactile Calm" design on every screen (soft raised / pressed surfaces, Plus Jakarta Sans, calm status colours) with purposeful motion from your animation-timing skill; friendly errors and loading / empty states; works on phones; README | Every screen checked live at laptop width and at 390px phone width; phone problems found and fixed (see `TESTING.md`) |

Automated tests: `python3 -m pytest -q tests/` → **578 passed** (249 before M7) (needs Python 3.10+, see README).

## Privacy test (two users)

- **Database level:** user A's project, pairs, checks, runs and results are invisible to user B (0 rows
  everywhere); B can't add to, rename or answer anything of A's; results can't be changed or deleted; no
  duplicates; no 4th worst-fail point. 16 of 16 steps passed.
- **Live app:** `tester.a+eval@example.com` creates a project; `tester.b+eval@example.com` gets an **empty
  list** and a **404** for A's project by its id. Passed (run twice).

## Bubl Solar results

**Run 1 (all 10 pairs, by script): 20 rows · 20 pass · 0 fail · 0 can't test.** 14 human checks are
waiting for you (layout, photos, checkout). With no fails, there were no "worst fails" to explain ("No fails
in this run").

That Run 1 had two problems in the app itself, now fixed:
1. Shopify hides a "Variant sold out or unavailable" label on every colour and only shows it when a colour
   really sells out. The app read it as visible text, so the AI wrongly said Sand and Rust Red were sold out
   (all three colours are in stock). That made #6 pass for the wrong reason.
2. One AI check (#10 phone) came back "AI could not judge, please look" because the free Groq plan allows
   about 8,000 words-worth a minute. The app now waits and retries.

**Run 3 (all 10 pairs, through the real screens, after those fixes): 20 rows · 18 pass · 2 fail · 0 can't
test.** The worst fails:
1. **#6 phone, colour change:** "The page only displays a price for the Black colour… Show the price and
   availability for each colour option before the add-to-cart button."
2. **#6 laptop, colour change:** the same finding on the laptop.

Be careful with this one: it's probably a limit of how we test. The app reads the page as it first loads.
It can't click the Sand or Rust Red swatch to see what changes, and all three colours are in fact the same
price and in stock. A person should check #6 on a real phone before Brajesh changes anything.

**Run 4 (re-run of #6, #8 and a new check from "Other changes"): 4 of 6 passed.** Good now? #6 **No**
(nothing on the real site changed, so that's the honest answer), #8 **Yes**, #11 "colours and Add to cart
on the Solaris page" **Yes**. Compare with Run 3: 6 same.

## What didn't work or needs you, in plain words

1. **Save your password.** Your account is `shresthahardik8@gmail.com`. The password is only in our chat,
   so put it in a password manager.
2. **14 human checks are waiting.** Open the newest run and press Looks right / Looks wrong after looking at
   bublsolar.com on your phone and laptop (menu overlap, photos and "Turn On" preview, checkout summary).
3. **Some shop behaviour can't be seen without a real browser.** By design the app reads pages with plain
   requests (no headless browser). So it can't click colour swatches (#6), open the photo zoom (#7) or reach
   the checkout page (#10). Those parts are human checks. If Brajesh's real problem is "the cart sometimes
   gets 5 lamps", that happens in the page's own scripts, and our cart test (which adds exactly once) can't
   reproduce it. #8 shows the cart itself counts correctly.
4. **Always read the AI's proposed check before approving it.** In Run 4 the AI first proposed opening
   `/products/solaris-black`, which doesn't exist. I discarded it and reworded the note.
5. **Bubl Solar now has 11 pairs** (#11 came from "Other changes"). If you want exactly 10, switch #11's
   Approved toggle off.
6. **Optional clean-up:** the smoke tests made throwaway accounts (`tester.a+eval…@example.com`,
   `tester.b+eval…@example.com`) with one test project each. They can't see your data. You can delete them in
   Supabase → Authentication → Users.
7. **Optional, for peace of mind:** your Groq key was pasted into this chat. It's stored only in Vercel
   (encrypted) and is in no file, repo, page or history. You can still make a new key at console.groq.com,
   since the chat log is saved on your Mac. If you do, paste the new one into Vercel → Settings →
   Environment Variables → `GROQ_API_KEY` and redeploy.

## Secrets check

No key or password in the repo, its whole history, or any file the live site serves. `/.env` and the server
code aren't reachable from the web. The Groq and Supabase keys exist only in Vercel's encrypted settings.
The browser never sees them, because it only talks to our own `/api` doors. No Supabase service-role key is
used anywhere. Details in `TESTING.md`.

## M7: the real browser replaces the human checks (19 Oct 2026)

**What changed.** For every check, on every device, code now picks the simplest way, in this order:
1. **Reading the page** (fast, free): page opens, words, counts, results, and AI questions on the page text.
2. **Real browser** (Browserless), only when a test needs a click or a look: "count after real clicks" and "AI looks at a
   screenshot". One visit per pair and device, phone then laptop, one screenshot shared, at most 12 visits per run.
3. **You, only as a last resort, always with the reason**: payment, login or "are you a robot?" page; the AI unsure twice;
   the browser unavailable, busy, out of units or too slow; or the 12-visit limit. Then "Looks right / Looks wrong".

The browser never types, pays, places orders, logs in or creates accounts; it refuses "Buy it now", "Pay", "Log in", "Sign
up" and similar, and closes marketing pop-ups like a shopper would. Screenshots are never stored.

**New needs (README):** 6 check clicks and looks without a person · 7 browser only when a plain read can't answer · 8 a
person only when the browser can't or mustn't go further, with the reason · 9 never pay, log in, create accounts or
order · 10 show which tests used the real browser.

**API changes (no new doors):** check rules `browser_count` and `ai_vision` with `steps` (doors 4, 5, 6, 7); door 9 routes
fetch → browser → person and returns `via` and `human_reason` per row; result checks carry `steps`; `/api/health` says
whether a browser key exists (`browser: true/false`, never the key). Database: migration `m7_real_browser`
(`checks.steps`, `results.via`, new rules). New AI job: Groq vision (`meta-llama/llama-4-scout-17b-16e-instruct`)
returns `{passed, why, confident}`.

**Bubl Solar now:** no `manual` checks left. #1 menu, #6 colour, #7 Turn On, #10 order summary → AI looks at a
screenshot; #8 add to cart once (priority) → count after real clicks = 1 (+ a screenshot check of the colour); #2–#5
and #9 stay plain page reads (their old manual checks became AI questions on the page text).

**How it was tested** (details in `TESTING.md`): 578 automated tests; the browser code run against bublsolar.com with
a local Chrome (every Bubl flow worked: menu, Sand, Turn On, exactly 1 in the cart, checkout stopped as a payment page,
"Buy it now" refused); and the live app with a copy of the 10 Bubl pairs (routing right, Run 1 untouched, the run
always finishes).

**Units used:** 0 Browserless units so far, because the live app has no Browserless token (below). Expected per full
Bubl run: 10 browser visits of 3–14 s each, so about **10 units** (1 unit = 30 s); a re-run of #8 alone: **2 units**.
The free plan's 1,000 units a month is enough for about 100 full runs.

**Didn't work / needs you:**
1. **The Browserless token is not in the project's Production settings.** I read the live server's settings by name
   only: it has `GROQ_API_KEY`, `SUPABASE_URL` and `SUPABASE_ANON_KEY`, and no Browserless token under any name. So
   on the live site every real-browser check is handed to you today with "The real browser isn't set up". Fix: Vercel →
   eval-copilot → Settings → Environment Variables → add `BROWSERLESS_TOKEN` (your token) for **Production** → Save →
   Deployments → ⋯ on the latest → Redeploy. Then `https://eval-copilot.vercel.app/api/health` shows `"browser": true`.
   To re-run my live test after that: GitHub → Actions → live-check → Run workflow (branch main, task `live`).
2. **The Bubl test ran on a copy, not your own account.** I never have your password, so the live tests used a throwaway
   account with an exact copy of your 10 pairs. Your own "Bubl Solar" has the same checks: press Run all.
3. **"Check out" on bublsolar.com does nothing in an automated browser**, so #10 opens `/checkout` directly; it then stops at
   the payment page and asks you, as designed.
4. **#6 phone failed in the live test on the old text question** ("only the Black price is shown"). With the browser on,
   the screenshot check sees the price change for Sand (₹1,970 vs ₹1,680), so treat that text question with care.

## Wording: real browser flow (19 Oct 2026)

Every screen now says how each check was done and why, in the same words everywhere: **Reading the page** (Code or
AI), **Real browser**, **You check**. Changes:
- **Results:** "How to read this" now explains how we check (simplest way first, real browser only for a click or a
  look) and each tag: Code, AI, Real browser, You check (last resort, always with a reason). "Result" and "Why" lines
  updated. Banner: "N checks need your eyes. We couldn't finish them ourselves, and the reason is on the card…".
  Handed-over cards show "Why we asked you: …" and "Your check"; pills read "Waiting for you" / "N waiting for you"
  (were "Needs a look" / "N to look at"); "Waiting for your answer." (was "Waiting for you to look at the site.").
- **Golden tests:** checks intro now says we use the simplest way and only a real browser for a click or a look, and ask
  you with a reason if we can't finish; kinds "Count after real clicks", "AI looks at a screenshot", "You check" (was
  "You look"); Steps hint "One step per line… It never pays, logs in or types into forms."; run time "about 10–30
  seconds per pair, up to a minute if it needs a real browser"; "review it, then save" (was "check it, then save").
- **Tags everywhere:** hover text explains each one (e.g. "Real browser: used because this test needs a click or a look").
- **My projects:** "Public link only. We never log in, pay or fill in forms on your site."
- **Server text:** an old manual check's note reads "You check: …" (was "You look: …").
- **README:** needs 6–10, the decision order, and the real browser in "How to use it", "How it's built" and "Safety".

## Landing page + dark theme (19 Oct 2026)

- **Landing page at `/`** (static, follows the Stitch design in the app's style): your headline and subtext, **Test
  yours** + "See how it works", three example tests from a made-up shop (desk lamp search pass/pass; one lamp added
  → phone fail "The cart showed 2 lamps after one tap"; open cart → laptop can't test, robot check), a "3 things to
  fix first" preview, How it works in 4 steps, a Run 1 vs Run 2 example and "Ready to test yours?". Every number on
  it sits inside a labelled example; no fake stats, no dead links, no fake URL box.
- **Routing:** log in / sign up moved to `/login` and `/signup`. After either you go to your projects (dashboard); the login is remembered, so the landing page then shows Dashboard. Logged out the top
  right shows Log in + Sign up and "Test yours" opens sign up; logged in it shows Dashboard and "Test yours" opens
  your projects. Opening a protected page logged out goes to `/login?next=…` and back there after logging in (only
  same-site paths are accepted).
- **Dark theme** from your palette: Primary #7A9CC6 for buttons and the switch, Secondary #5B7FAE for the switch
  track, Tertiary #8FA792 for "pass", Neutral #1A202C for cards. Text contrast is AA or better everywhere measured.
  It follows the device at first; the **Dark theme** switch sits in the avatar menu between "Signed in as" and
  "Log out", and the choice is remembered on that browser. Light theme unchanged.
- **Tested live** on both a laptop and a phone size, logged out, with a brand-new account, and after logging out
  (TESTING.md). Commits: "Landing page groundwork…", "Landing page…", "Dark theme…".

## Decisions I made on my own (full list in `DECISIONS.md`)

- **Supabase:** talked to with plain requests as the logged-in user, so the privacy rules always apply. No
  admin key. Two advisor fixes: locked a Supabase helper, and added 3 indexes.
- **Speed:** one AI call per pair per device (phone and laptop in parallel), with a 50-second budget per
  pair, to stay under Vercel's 60-second limit.
- **Outcome rules:** a block (403 / 429 / challenge page) means "can't test", never fail. A page that
  doesn't load is a fail. All-human or AI-unsure rows are "can't test" until you answer.
- **Locked checks:** checks lock once a pair has run, because old results point at them. To change them,
  add a new pair.
- **Fixed 4 AI-written checks before Run 1:** they could never be true or false on the real pages (e.g.
  "the cart must not contain a 5", which fails on any price with a 5 in it).
- **Shopify's hidden "sold out" labels are ignored, and the app waits when Groq says "too many requests"**
  (found in Run 1).
- **Your design, honestly:** kept the look of your Stitch mockups but left out decoration with no real
  feature behind it, such as "Forgot?", "All systems operational", "Overall health 92.5%", the staging
  server log and "Download diff log". The build rules forbid invented features and made-up numbers.
  Deepened the blue slightly so white button text is readable (AA contrast). Light theme only, like the
  mockups. Lucide icons instead of Material Symbols, and no Tailwind (no build step).
- **Motion, per your animation skill:** only movement and fading (no layout jumps), smooth ease-out curves,
  one signature moment per screen (on Results, each row slides in and its status pops as the pair
  finishes), and nothing moves if your phone or computer asks for reduced motion.
- **Phone layout:** checked every screen at 390px. Crumbs shorten, tap targets are at least 44px, the
  "Run all" bar is compact, and "How to read this" starts closed on phones.

## How it was built

Opus (lead) planned, reviewed every change, ran all tests, and alone touched Supabase, Vercel, git and your
Groq key. Sonnet sub-agents built the screens, the site reader, the AI helper and the phone fixes; Haiku
sub-agents did the README and the secret scans. See `PLAN.md`.
