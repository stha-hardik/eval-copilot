# Kole UI/UX rules digest (for Eval Co-pilot)

Source: https://github.com/stha-hardik/kole-uiux-skills (shallow clone at `scratchpad/kole-uiux-skills/`).
Read in full: `SKILL.md`, `kole-component-polish/SKILL.md`, `references/kole-principles.md`,
`references/color-and-levels.md`, `references/animation.md`, `README.md`, `SOURCES.md`,
`kole-component-polish/README.md`, `references/visual-examples/README.md`.
Not inspected: the ~80 PNG/WEBP frames under `references/visual-examples/` (listed only).

Two skills, one shared rule set:
- **kole-uiux-eval** (`SKILL.md`): architecture pass, score 11 dimensions, recommend, co-build whole screens.
- **kole-component-polish**: surgical fixes to named components only, plus a micro-flaw checklist.

The skill gives **no hex values anywhere**. Colour is given as "% white" steps, OKLCH, and Tailwind step names.
The only hex in the sources is the skill's own example: "11% white (≈#1a1a1a)".

---

## 0. How to apply it (process rules)
- **Architecture pass first.** Identify the surface type, then check for structure Kole expects but the screen lacks.
  "These absences are findings even when nothing on screen is 'wrong.'"
- **Embedded-host rule.** If the app runs inside a host frame (Whop, Shopify, extension panel, iframe), do not add a
  sidebar. Treat it as a single-purpose utility: one job, one primary action, empty states, bulk actions.
- **Posture: "redesign, don't just polish."** Move, regroup, add, remove. "Prefer removing/simplifying over adding,"
  but add structure Kole expects when it is absent.
- **Judge at real size on the target device**, not zoomed out. Check hidden states (open menus, hover, empty, error).
- **Output shape (eval):** `Surface type`, `Maturity: Level X/4 · Score: NN/33`, Missing structure, Restructure,
  Strengths, Issues ranked by impact (each tied to a dimension, with an exact fix), Biggest single win.
  "Never invent gaps to fill them."

## 1. Layout & spacing
- **4-point or 8-point base grid.** "Everything a multiple." Keep small elements strictly on the grid. Large sizes can
  round to 5/10.
- **Default rhythm ~32px between items.** Group related items closer: "proximity = relationship."
- **White space beats excessive grids.** Grids are "guidelines, not law." Responsive ~12 / 8 / 4 columns
  (desktop / tablet / mobile), mainly for repeating content.
- **"Fewer containers and fewer lines."** No double-nested cards (padding-on-padding cramps content).
- **Dashboards:** "stricter grids" and tighter spacing than landing pages.
- Max widths and section padding values: **not specified** in the sources.

## 2. Typography
- **One sans-serif.** Named options: DM Sans, Geist, Inter, Manrope, Space Grotesk, SF Pro. Two families are fine
  (display + sans). Three is "pushing it"; four "is asking for problems."
- **No serif or decorative font for UI or body text.** A display/handwritten face used for body text is a "design sin."
- **Size range:** landing pages ≤6 sizes, wide range. Dashboards: "smaller range, rarely >24px."
- **Scale:** ratio off a 16px base: 1.618 (golden), 1.27 (√golden, full scale), or cube-root (dense UIs / mobile).
- **Line-height:** body ~150%; headings 110–130%. Large text (>~70–80px): letter-spacing −2% to −4%,
  line-height 110–120%.
- **Weights and colours:** max **2 weights** (separated by at least one step) and max **2 colours**
  (primary + the same colour at 40–70% opacity). Avoid ultra-bold/ultra-thin for regular text.
- **Hierarchy** comes from size + position + colour, and weight + colour more than size alone.
- **Mobile base:** iOS 17px, macOS 13px. Mobile text is "similar or larger," not smaller.
- **Fix order** after importing or generating UI: "fonts, alignment, and colour."

## 3. Colour
### Palette approach (4-layer system replaces 60-30-10)
"60-30-10 is fine for beginners and landing pages, but product design needs more." Reference: Vercel is ~90% black,
~8% white, ~2% red.
- **Layer 1 Neutral foundation.** A product UI needs ~4 background layers, 1–2 strokes, ~3 text variants.
  - Backgrounds mostly near-white (Linear ~99%, Notion 100%, Vercel ~98%). App frame/sidebar is "a slightly darker anchor."
  - Card edge: **~85% white**, "not thin black borders," and not a drop shadow.
  - Buttons: multi-purpose buttons ~90–95% white. "The more important the button, the darker it is."
  - Text: headings ~11% white; body ~15–20% white; subtext ~30–40% white.
- **Layer 2 Functional accent (a scale, not one colour).** Main = 500/600; hover = 700; link = 400/500.
  Dark mode: primary = 300/400; hover = 400/500.
- **Layer 3 Semantic.** "blue = trust, red = danger/urgency, yellow = warning, green = success."
  Destructive actions are **red, never the brand colour** ("a design sin"). Colour must encode state.
- **Layer 4 Theming.** For each neutral: lightness −0.03, chroma +0.02, then adjust hue.
- **HSB trick:** each shade +20 saturation / −10 brightness. Dark-mode depth: raise brightness ~4–6 and lower
  saturation 10–20 per layer.
- **Tailwind shorthand:** light bg = `50`, accent = `500`; dark primary = `300`, dark bg = `950`.
- **Neutral-first:** "Use colour for purpose, not decoration." Icons mostly need no colour. Prefer grey over pure
  black/white. Off-whites in light mode; bluish-blacks in dark mode.
- **Less is more:** "multiple accent colours compete." Use one earned accent.

### Dark mode
- "Not the inverse of light mode." Inverting makes contrast too high.
- No shadows in dark mode. Show depth with **surfaces that get lighter as they elevate**, or with borders.
- Dark neutrals need about **double** the spacing of light ones (light ~2% steps → dark ~4–6%).
- Reserve pure white for the most important text and actions. Dim or desaturate bright chips and logos.

### Contrast
- **AA contrast (WCAG)** on all text and status colours. Do not rely on colour alone to signal status.
- Badges and chips: "bright pill + white text" fails. Darken the fill or use dark text.

## 4. Buttons & inputs
- **Hierarchy:** "Only one primary CTA per header section." Secondary = outline, no background, or reduced opacity.
  Ghost buttons have no background until hover. (Note: the rule is per section, not per whole screen.)
- **Padding:** "width = 2× height" guideline.
- **Icon size ≈ line-height** (e.g. 24px for ~24px line-height). Icons are usually too large.
- **Button states:** at least four: default, hover, active/pressed, disabled (+ loading).
  Hover = lighter/brighter base; active = darker; disabled = desaturated. Mobile has no hover; use a darker press state.
- **Buttons should almost always have a small animation** (see §10).
- **Radius:** one corner radius reused (example: 10px for small elements). Nested radius = outer − gap.
  Pill shapes need no fix.
- **Chips are not buttons:** never coloured like the primary CTA; vertically thinner; vertical padding = ¼ to ½ of
  horizontal padding.
- **Pick-one controls** (All / 1M / 3M / 1Y) go in **one segmented-control container**, with the active option as a
  solid pill inside it. Detached floating pills are wrong. Multi-select tags can stay as separate chips.
- **Inputs:** need focus state, error state (red border + message), and sometimes warning.
- **Forms:** labels **above** inputs (always visible); real placeholder examples; a subheading; a link to the alternate
  action; off-white input background with a reduced-opacity stroke; 4px grid.
- **Matching CTAs:** same label means same destination.

## 5. Cards, tables, lists, badges
- **Cards:** group with whitespace, not nested containers. "Sometimes the best background is none (a border)."
  "Cards/elements that do nothing → delete them."
- **List separation, best to worst: space > dividers > colour.**
- **Tables:** "need search/filter/sort." Use bulk actions on multi-select. Use optimistic UI.
- **Four reusable components:** lists/tables, cards, inputs, tabs.
- **Tabs:** "tabs add pages without cluttering the sidebar."
- **Dense-row recipe ("breathe + ⋯ menu")** for cramped rows:
  - Add vertical padding; let content set row height.
  - One primary action visible, right-aligned (e.g. Send). Secondary actions go into a ⋯ overflow menu.
  - Wordy controls become icons or chips. Group meta (date, tier) into one cluster.
  - **The ⋯ menu must render above the row/card** (portal or z-index). Do not let `overflow: hidden` clip it.
- **Status pills / badges:**
  - Colour must encode state (completed vs in-progress). "Same colour for every status" is an AI tell.
  - Prefer a % number over a vague label.
  - Must pass AA contrast. Chips must never use the primary CTA colour.

## 6. States
- "When a user does anything, there should be a response."
- Provide **loading** spinners, **success** messages, and **empty** states "everywhere."
- Empty states must cover **both first-run and no-results**.
- **Error:** red border plus message on inputs. Toast for warnings and errors without taking over the screen.
- **Acknowledge instantly:** grey out a button on click while the next state loads.
- **Optimistic UI:** update immediately, then reconcile with the server (Gmail/Apple Mail model).
- **Confirm actions:** modal + toast pair. Modal must confirm or cancel. Toast confirms the change.
- **Visible focus** states on everything interactive (accessibility floor).
- **Exercise hidden states:** open ⋯ menus and dropdowns, add or select items, hover, expand/collapse, and trigger
  empty, first-run, loading, error, and success. "A fix that looks right in the static view but breaks when a menu
  opens or a row is added isn't done."

## 7. Copy & microcopy
- "Prefer friendly, natural copy over corporate jargon." Shorter, punchier copy.
- Landing pages: copy shifts from "what it does" to "how it helps" (Level 4).
- Labels above inputs; real placeholder examples, not generic text.
- **Test with real/edge content:** long names truncate (not crushed to "Member v80…"). Long strings should not break
  layout.
- **Icon-only** only for well-known icons (house, bookmark, user). Otherwise add a tooltip (hover delay ~1000ms).
- The skill's own output style: explain changes in plain language, name the exact element and exact value.

## 8. Mobile / responsive
- **Touch target ≥44px.** Bottom bar 3–4 links ideal, 5 max.
- **One screen, one job.** A new need gets a new page, not a busier layout. Bottom sheets keep context.
- Four building blocks only: cards, text/links, images, inputs. Do not double-nest cards.
- Press state instead of hover. Active bottom-nav icon must stand out; inactive icons stay visible but de-prioritised.
- Gestures: swipe-back moves background ~35%; long-press = right-click (blur + slight zoom); swipe-down dismisses sheets.
  Slide-to-confirm for high-impact, irreversible actions.
- Empty states for first-run and no-results.
- Check at real size on the target device (mirror on mobile, 100% on desktop).

## 9. Icons, shadows, borders, radius
- **One icon family only.** Default: `lucide-react` (24px, 2px stroke). Alternatives: Phosphor (one weight), Heroicons
  (outline or solid, not both), Tabler, Feather.
- **Replace EVERY existing icon on the screen** with the same family, not just new ones.
- **No emojis as icons, no hand-drawn inline SVGs, no mixed sets.** "A Send arrow that doesn't match the Settings gear
  is a fail."
- **Shadows:** "If the shadow is the first thing you notice, you're not using it right."
  - Opacity 15–20%, with higher blur and a light-grey colour.
  - Offset x ≤ y; blur = 1.3–2× y.
  - Strength scales with elevation: overlays > cards. Darker backgrounds need stronger shadows.
  - If a shadow or gradient isn't working, remove it.
- **Gradients:** one hue family only (e.g. light/dark of one hue). Most often none at all.
- **Image overlays:** gradient or progressive blur, not a flat scrim.
- **Borders:** ~85% white edges, not thin black.

## 10. Motion (`references/animation.md`)
- **Purpose over decoration.** Motion should confirm an action, smooth a transition, guide attention, or reveal
  progressively. "Don't animate everything." Pick one signature moment.
- **Durations:** 100–150ms press/toggle feedback; 200–300ms state change (hover, menu); 300–500ms layout
  (accordion, modal); 500–800ms entrance. **Exit ≈ 75% of enter.** Feedback >500ms is a "never."
- **Easing:** "almost never want a linear ease." Default `cubic-bezier(0.25, 1, 0.5, 1)` (ease-out-quart).
- **Spring** only for gestures, draggable/stacked cards, and signature moments (Kole example: stiffness 636, damping 24).
  Never elastic overshoot. Spring is not used on routine state changes.
- **Animate only `transform` and `opacity`.** Never width/height/top/left. Target 60fps.
- **`prefers-reduced-motion` is mandatory.**
- **Scroll-jacking:** "sparingly, if ever."

## 11. Charts & dashboards
- **Charts:** always include axis labels, gridlines, a time/range selector, and a brief title or summary.
- **Never:** curved data lines; faded data lines; rounded bar tops; decorative bars with no meaning; more bars than
  data points.
- **Multi-series colour:** OKLCH for equal perceived brightness. Set lightness and chroma, then step hue ~25–30 per series.
- **Income vs expenses:** two-sided bar chart (up = income, down = expenses).
- **Dashboard structure:** sidebar "spine" (grouped nav, settings/help at bottom, active-state indicator, collapsible)
  + top bar for page actions + main area for what matters most. Not applicable if embedded in a host.
- **Widget priority tiers:** high = top-left, mid = middle, low = bottom-right. The most important item is visible
  without scrolling. Do not mix priority levels randomly.
- **Context, not clutter:** data and meaningful imagery add context. Decorative elements are clutter.
  "Removing things can make a page feel empty rather than clearer."
- **No repeated KPI rows.** Consolidate duplicate metrics. Keep only the 1–2 stats that matter.
  "Don't show data twice."
- **Embedded single-purpose utility:** "resist padding the top with a row of mostly-zero KPIs."

## 12. Scoring rubric & checklists
- **11 dimensions, each 0–3** (0 wrong/absent, 1 beginner, 2 solid, 3 Kole-grade). Max 33:
  1 Affordances & signifiers · 2 Visual hierarchy · 3 Grids/layouts/spacing · 4 Typography · 5 Colour theory ·
  6 Dark mode · 7 Shadows · 8 Icons & buttons · 9 Feedback & states · 10 Micro-interactions · 11 Overlays.
- **Maturity map (landing-page definition, indicative elsewhere):** ≤16 = L1 template · 17–24 = L2 identity ·
  25–30 = L3 craft · 31–33 = L4 detail.
- **Beginner tells:** unplanned flow (no search/skip/empty path); overused effects; tight spacing; inconsistent
  components or radii; mixed or bad icons; redundant elements; missing interactive feedback; over-designed charts.
- **AI / vibe-code tells:** emojis as icons; AI-picked clashing colours; repeated KPI rows; same colour for every
  status; chips failing contrast; gradient initial-avatars; sparse modals; dead elements; 5+ pricing plans; generic layouts.
- **Micro-flaw checklist** (polish skill): spacing off-grid or eyeballed; mismatched radii; large text not tightened;
  >2 weights or >2 colours; accent used decoratively; destructive not red; pure black/white; contrast below AA;
  shadow too strong; mixed or wrong-size icons; more than one primary button; chip too tall or primary-coloured;
  missing hover/active/focus/disabled; detached pills that should be one control; dividers that should be space;
  double-nested cards; misaligned edges.

## 13. Consolidated "never" list
- Serif, decorative or handwritten face for UI or body text; more than 2 weights or 2 colours per text level.
- Pure #000 or #fff for backgrounds or main text. Dark mode made by inverting light mode.
- Destructive actions in the brand colour. Emojis as icons. Mixed icon sets. Hand-drawn SVG icons.
- Thin black borders; drop shadows as the only edge definition; a shadow that is the first thing you notice.
- Double-nested cards; detached pills for pick-one controls; dividers where space would do.
- Curved or faded data lines; rounded bar tops; decorative bars; more bars than data points.
- Linear easing; animating layout properties; feedback over 500ms; animating everything; scroll-jacking; elastic overshoot.
- Stock or unrelated imagery; colour applied to anything that will take it; 5+ pricing plans.
- Gradient initial-avatars; repeated KPI rows; cards or elements that do nothing.
- Clipped overflow menus; a sidebar inside an embedded host; ignoring reduced-motion.

---

## Rules most relevant to a data-heavy dashboard/table app
1. **Structure:** sidebar spine + top bar for page actions + main area led by the most important data. Skip the
   sidebar if the app is embedded in a host frame.
2. **Settings and multi-section screens are never one flat list.** Split into grouped panels or tabs.
3. **Tables need search, filter and sort.** Add bulk actions for multi-select, and use optimistic UI on row actions.
4. **Dense rows:** breathe, one right-aligned primary action, the rest in a ⋯ menu rendered above the row (no clipping).
5. **List separation: space > dividers > colour.** No double-nested cards; fewer lines and containers.
6. **Pick-one filters are one segmented control,** not detached pills.
7. **Charts:** axis labels, gridlines, range selector; straight lines; no rounded bar tops; no more bars than points.
   Multi-series colour via OKLCH with hue steps of ~25–30.
8. **Colour encodes state.** Status colours are semantic (green success, red destructive, yellow warning). Status is
   never colour-only. Every badge passes AA contrast.
9. **One earned accent, used as a scale** (500/600 main, 700 hover). Neutrals dominate: ~4 background layers,
   ~85% white edges, text ~11% / ~15–20% / ~30–40% white.
10. **Dark mode is designed, not inverted:** no shadows, lighter surfaces as elevation rises, double neutral step size,
    no pure #000 or #fff.
11. **Type:** one sans-serif; dashboard size range is small (rarely >24px); body ~150%, headings 110–130%;
    max 2 weights and 2 colours per level.
12. **One icon family** (`lucide-react`, 24px, 2px stroke), with every icon on screen replaced. No emojis.
13. **Every state has a design:** loading, empty (first-run and no-results), error, success; four button states plus
    visible focus; toast after actions; grey-out on click.
14. **Priority layout:** most important KPI or table top-left, visible without scrolling; deduplicate KPIs and data.
15. **Shadows:** 15–20% opacity, soft, light-grey, x ≤ y and blur 1.3–2× y, or none. Overlays get more than cards.

---

## Caveats
- No hex palette exists in the skill. Choose hex values from the % white and OKLCH rules above.
- Spacing scale is 4/8px. The skill does not give max widths, section padding, or container widths.
- Beginner-tells section says "his 7 mistakes" but lists 8 items.
- `references/visual-examples/README.md` names thumbnails that are not in the repo (e.g. `4 levels.png`,
  `Software colors.png`, `Mobile App UI.png`, `UI Elements.png`, `Sidebar Tutorial.png`, `Vibe Coded SaaS.png`).
  The `projects/` frames (61 files across 10 folders) are present.
- `animation.md` points to an external `i-animate` companion skill that is not in the repo.
