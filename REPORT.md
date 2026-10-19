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

Automated tests: `python3 -m pytest -q tests/` → **249 passed** (needs Python 3.10+, see README).

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
