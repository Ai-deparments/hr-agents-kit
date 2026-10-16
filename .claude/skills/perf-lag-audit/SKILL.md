---
name: perf-lag-audit
description: >
  Find and fix lag, jank and heavy assets in any web app, Telegram Mini App or
  bot (not tied to one repo). Use whenever the user says something lags, is
  slow, freezes, stutters, animations are choppy or parts of an animation
  disappear, scrolling jerks, the page/app is heavy or loads long, a bot answers
  slowly — "лагает", "тормозит", "медленно", "дёргается", "тяжело грузится",
  "анимации лагают/стираются", "sekin ishlayapti", "qotib qolyapti" — or asks to
  compress images/emoji/animations "without losing quality", or to make the app
  feel light and smooth. Measure first, fix the measured culprit, prove it with
  before/after numbers.
---

# Perf / lag audit

Rule zero: **no fix without a number**. Measure, change one thing, measure again.
A fix that is not visible in the numbers is a guess — say so.

## 1. Reproduce on a "phone"

Desktop Chrome hides most lag. Always measure with CPU throttling in Playwright
(Chrome DevTools Protocol), phone viewport and DPR:

- ×2 throttle ≈ mid-range phone, ×4 ≈ low-end phone (Telegram users in UZ/CIS).
- Viewport 390×844, `deviceScaleFactor: 2.6`.
- Run `scripts/fps.mjs` (this skill) against the page/route:
  `node fps.mjs <url> [cpuRate=4] [scroll=1]` → UI fps, long frames (>50 ms),
  DOM mutations/s, running animations. Copy the script next to a local
  `node_modules` with `playwright` (or `npm i playwright` in a scratch dir).
- Compare with `prefers-reduced-motion: reduce` (the script's `--still`): if the
  page is smooth "still" and janky "animated", animations are the culprit; if
  both are janky, it is layout/paint/JS.

Targets: UI ≥ 50 fps at ×2, no long frames while idle; scrolling ≥ 45 fps at ×4.

## 2. Find the culprit (checklist, in order of how often it is the cause)

**Animations (Lottie / SVG / CSS)**
- How many Lottie players exist and how many render each frame? Each SVG player
  rebuilds hundreds of nodes per frame; 4+ complex ones at 60 fps kill a phone.
- Does every player run its own `autoplay`/rAF loop? → one shared scheduler.
- Are players destroyed/re-created on scroll (IntersectionObserver start/stop)?
  Re-creating a heavy SVG mid-scroll = jank. Create once, then just don't render.
- Off-screen / hidden-tab / during-scroll rendering?
- Infinite CSS animations of `filter`, `box-shadow`, `background-position`,
  `width/height/top/left` (paint/layout every frame) instead of transform/opacity.
- Animation started on `click` in Telegram WebView arrives late together with
  the route change → start it on `pointerdown` with Web Animations API.

**Rendering / CSS**
- `backdrop-filter` blur on large or many layers (Android Telegram WebView may
  even crash: "Aw, Snap!") — solid fallback under an `is-android` class.
- Huge `box-shadow`/`filter: blur` on scrolling content, fixed full-screen
  gradients repainting on scroll, missing `contain`.
- Layout thrash: reading `offsetWidth`/`getBoundingClientRect` after writes in
  loops; long lists rendered at once.

**Assets / network**
- Measure transfer size (gzip/brotli), not file size — and on the **production
  build** (`vite build && vite preview`, or the deployed URL): dev servers send
  libraries unbundled (e.g. the whole icon pack, 700 KB) and mislead.
- Images: re-encode WebP q≈80–82 `effort 6`, keep only if ≥5% smaller; resize
  to display size × 3 DPR max; PNG palette; JPEG mozjpeg q80.
- Lottie JSON: round path vertices (`v/i/o` in shapes) to 0.1 px of a 512 canvas,
  everything else to 3 decimals, **never touch easing** (`i/o` objects in
  keyframes); minify. Typically −25% gzip. Verify by pixel-diffing frames
  (all frames, not 3) — differences must be edge antialiasing only (<0.5%).
- Do not convert animations to animated WebP/GIF blindly: 90 frames ≈ 400 KB per
  emoji vs ~60 KB gzipped Lottie.
- Fonts: self-host, one variable file, `font-display: swap`.

**Bots / backend (slow answers)**
- Sequential awaits that could be `asyncio.gather`/`Promise.all`.
- Cold DB pool (min_size 1, TLS on first query) → keep a few warm connections.
- Remote DB round-trips per command; missing indexes on hot WHERE/JOIN columns
  (e.g. `referred_by`, `user_id`) → index in startup migrations.
- Bot calling its own backend through the public internet/CDN while both run on
  one machine → call `127.0.0.1:PORT`, keep-alive HTTP client.
- Per-update Telegram API calls that can be cached (`getChatMember`, channel
  lists) with a short TTL; cache only the positive answer.

## 3. Fix patterns that worked

- **Shared animation scheduler** (one rAF for the whole app): every visible
  animation plays (never freeze some into "just a picture" — users read that
  as broken), each at most 30 fps, and a **time budget per screen frame**
  (~6 ms): render the longest-waiting first, stop when the budget is spent.
  Per-entry time, so speed is constant and weak phones just get fewer frames.
  Skip while scrolling (+200 ms) and when `document.hidden`.
- **Do NOT gate decorative emoji on `prefers-reduced-motion`**: phones often
  have "reduce animations"/battery saver on; everything froze. Check the
  global reduce rule: `* { transition-duration: .01ms }` with the default
  `transition-property: all` turns every Lottie/SVG attribute change into a
  CSS transition (3× slower). Scope it `:not(svg *)`. Always measure with
  `--still` too.
- **Create once, render selectively**: players live while their screen lives;
  the scheduler decides what draws.
- Result reference (Mini App grid with 8 heavy animations all playing): CPU ×2
  UI 54 fps, each animation 15 fps; ×1 60/27; reduce-motion bug 21 → 60 fps.
- Count *moving* animations, not just fps: a fix that freezes animations
  "wins" fps and fails the user.

## 4. Verify and report

- Re-run the same measurement; show a before/after table (fps, long frames,
  transfer KB).
- Click-through regression: every button on every screen still works, no JS
  errors (Playwright crawl).
- Visual check: screenshots/frames compared; nothing disappears.
- Document the rule in the project's CLAUDE.md/AGENTS.md so the next agent
  does not re-introduce `autoplay` per player or re-encode with a worse codec.
- Report to the user in plain words: what lagged, why, what changed, the numbers,
  and what was not measurable (real device, network).
