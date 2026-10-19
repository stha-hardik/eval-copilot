# Eval Co-pilot: what the whole app has been

**Live:** https://eval-copilot.vercel.app · **Code:** https://github.com/stha-hardik/eval-copilot (public)

## The idea

A builder thinks their website (or AI feature) works because they only tried the things they picked. Eval Co-pilot
takes up to 10 **golden pairs** (what a user does + what a good result has), runs every one against the **live** site
as a **phone** and as a **laptop**, marks each pass / fail / can't test with a one-line why, picks the **3 worst
fails** and says what to change, and keeps **Run 1 next to Run 2** so the builder can prove a fix worked.
First real user: Brajesh, who runs the Shopify store bublsolar.com.

**The win:** change something on the site → tick it → **Re-run changed** → the case that failed now says **FIXED**
and **"Good now? yes"**, with Run 1 still there untouched.

## How it's built

| Piece | Choice |
|---|---|
| Screens | Plain HTML + CSS + vanilla JS (no build step): landing, log in / sign up, My projects, Golden tests, Results (with re-run, "Good now?", compare) |
| Design | The owner's "Tactile Calm" look (soft raised / pressed surfaces, Plus Jakarta Sans, calm sage / terracotta / amber status colours), light + dark theme, one shared component system with purposeful motion, works on phones (bottom tab bar) |
| Server | One Python FastAPI app on Vercel, 14 doors (+ a demo door for the audit) |
| Login + data | Supabase (email + password, Postgres, row-level security on all 8 tables; results can only be added, never changed) |
| AI | Groq: `openai/gpt-oss-120b` tidies pairs, suggests pairs, judges AI checks, explains the worst fails, turns "other changes" into checks; `qwen/qwen3.8-27b` looks at screenshots |
| Reading the site | Python `requests` for plain page reads; **Browserless** (hosted real Chrome) only for simple clicks: one page + at most one click, before / after screenshots |

## How each check is decided

**Code** decides what code can (page opens, words present / absent, counts, cart contents, pass counts, the 3 worst,
FIXED / BROKE). **AI** decides meaning (does the answer give the price? does the screenshot show the lamp lit?) and
always writes its reason. **Real browser** does one click and takes the pictures. **You check** is the last resort,
always with the reason (payment page, login page, captcha, AI unsure or busy). Blocked by the site = "can't test",
never "fail".

## How it got here

1. **Build (cloud session):** spec in `BUILD_PROMPT.md`, all doors, screens, database with RLS, 244 tests; couldn't
   deploy there (network blocked).
2. **Deploy and prove (laptop):** Vercel settings, live two-user privacy test, owner's account, Brajesh's 10 Bubl
   pairs, live runs and re-runs, two real bugs fixed, report.
3. **Owner's design:** Tactile Calm redesign with motion, checked on phone and laptop; then a proper component system
   with the missing mockup parts built from real data only.
4. **M7 real browser + landing page + dark theme** (another session), then connecting Browserless live, switching to
   Groq's current vision model, before / after screenshots, phone click fixes, and the owner's rule that the browser
   only does simple one-click checks.
5. **Audit:** 93/93 security probes, every feature and error state tested live, and a demo AI app with a planted flaw
   to prove the tool can test **AI features** too (caught → fixed → FIXED).

## Where it stands (20 Oct 2026)

- **Bubl Solar, final run (Run 12):** 22 rows, **20 pass, 2 fail, 0 can't test**. The fails are #6 (picking Sand
  shows no price or stock for that colour on the page as first loaded). The real browser adds exactly one Solaris to
  the cart on phone and laptop.
- **Demo AI app:** planted "no prices" bug caught in Run 1, fixed, re-run → **4 FIXED, Good now? yes**.
- **591 automated tests** pass.
- **Main limits:** Groq's free plan covers about 5–6 full runs a day with screenshot answers. A person's "Looks wrong"
  doesn't change a row's outcome yet. There are no per-account usage limits.
- **Human to do:** classmate test with Brajesh, stranger test, 3 hand grades of the AI judge, paper sketches,
  submission template.

Full detail: `AUDIT.md` (audit), `02.2.md` (this session's log), `REPORT.md`, `TESTING.md`, `DECISIONS.md`.
