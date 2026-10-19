// Shared UI components (exposed as EC.ui). Loaded on every page right after /js/api.js.
// Styles and motion live in /css/app.css; this file only adds the behaviour that CSS cannot do.
//   EC.ui.topbar(opts)        shared top bar + tabs + bottom tab bar + avatar menu
//   EC.ui.remember(opts)      remember the last project / run (localStorage, always in try/catch)
//   EC.ui.segmented(el)       sliding-indicator segmented control (emits "change")
//   EC.ui.tabs(el)            same indicator, for links
//   EC.ui.iconToggle(el)      pressed/unpressed icon button, with a small pop; .set(btn, on) for page code
//   EC.ui.disclosure(details) animated <details> (also works on every details.disclosure automatically)
//   EC.ui.menu(button, menu)  popover menu
//   EC.ui.switchHtml / iconToggleHtml / pill   markup helpers so pages never repeat markup
//   EC.ui.checkKind / checkTag / stepsText     who decides a check (Code / AI / Real browser / You check) + browser steps in plain words
// Every animation here is skipped when the reader prefers reduced motion.
(function () {
  "use strict";
  var EC = window.EC = window.EC || {};
  var ui = EC.ui = {};

  function esc(v) {
    if (EC.esc) return EC.esc(v);
    return String(v == null ? "" : v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function reduced() {
    return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }
  ui.reducedMotion = reduced;
  function sget(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function sset(k, v) {
    try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, String(v)); } catch (e) { /* private mode */ }
  }
  function icons() { if (window.lucide && window.lucide.createIcons) window.lucide.createIcons(); }
  function arr(list) { return Array.prototype.slice.call(list); }

  // ------------------------------------------------------------------ sliding indicator
  // One raised element that slides to the active item (FLIP: it is placed at its new rect at once, then
  // started from the old rect with a transform and released, so only `transform` is ever animated).
  function slider(container, activeSel) {
    if (container._ecSlider) return container._ecSlider;
    var ind = container.querySelector(":scope > .seg-indicator");
    if (!ind) {
      ind = document.createElement("span");
      ind.className = "seg-indicator";
      ind.setAttribute("aria-hidden", "true");
      container.insertBefore(ind, container.firstChild);
    }
    var last = null;

    function place(animate) {
      var el = container.querySelector(activeSel);
      if (!el || !el.offsetWidth) { ind.classList.remove("is-ready"); last = null; return; }
      var r = { l: el.offsetLeft, t: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight };
      var ready = ind.classList.contains("is-ready");
      var go = !!(animate && last && ready && !reduced() && (last.l !== r.l || last.t !== r.t || last.w !== r.w || last.h !== r.h));
      if (go) {
        ind.style.transition = "none";
        ind.style.transform = "translate(" + (last.l - r.l) + "px," + (last.t - r.t) + "px) scale(" + (last.w / r.w) + "," + (last.h / r.h) + ")";
      }
      ind.style.left = r.l + "px";
      ind.style.top = r.t + "px";
      ind.style.width = r.w + "px";
      ind.style.height = r.h + "px";
      ind.classList.add("is-ready");
      if (go) {
        void ind.offsetWidth;
        ind.style.transition = "";
        ind.style.transform = "";
      } else {
        ind.style.transition = "none";
        ind.style.transform = "";
        void ind.offsetWidth;
        ind.style.transition = "";
      }
      last = r;
    }

    var seen = typeof WeakSet === "function" ? new WeakSet() : null;
    var ro = null;
    function observe() {
      if (!window.ResizeObserver) return;
      if (!ro) ro = new ResizeObserver(function () { place(false); });
      if (seen && !seen.has(container)) { seen.add(container); ro.observe(container); }
      arr(container.children).forEach(function (c) {
        if (c === ind) return;
        if (seen && !seen.has(c)) { seen.add(c); ro.observe(c); }
      });
    }
    function refresh() { observe(); place(false); }

    var api = { place: place, refresh: refresh, indicator: ind };
    container._ecSlider = api;
    refresh();
    if (window.requestAnimationFrame) window.requestAnimationFrame(function () { place(false); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { place(false); });
    window.addEventListener("load", function () { place(false); });
    window.addEventListener("resize", function () { place(false); });
    return api;
  }

  // ------------------------------------------------------------------ segmented control
  // Markup: <div class="segmented" role="group"><button class="segmented-btn" data-value="x" aria-pressed="true">..</button>..</div>
  // (use role="tablist" + role="tab" + aria-selected for tab semantics). Emits a bubbling "change" CustomEvent
  // with detail {value, el}. Arrow keys / Home / End move the selection.
  ui.segmented = function (el, opts) {
    if (!el) return null;
    if (el._ecSeg) return el._ecSeg;
    var attr = el.getAttribute("role") === "tablist" ? "aria-selected" : "aria-pressed";
    function items() { return arr(el.querySelectorAll(".segmented-btn")); }
    function valueOf(b) { var v = b.getAttribute("data-value"); return v != null ? v : String(items().indexOf(b)); }
    function current() {
      var f = items().filter(function (b) { return b.getAttribute(attr) === "true"; });
      return f[0] || null;
    }
    var sl = slider(el, ".segmented-btn[" + attr + '="true"]');
    function sync() {
      var cur = current();
      items().forEach(function (b) {
        b.setAttribute(attr, b === cur ? "true" : "false");
        b.tabIndex = !cur || b === cur ? 0 : -1;
      });
    }
    function select(target, o) {
      var b = typeof target === "string"
        ? items().filter(function (x) { return valueOf(x) === target; })[0]
        : target;
      if (!b) return;
      var changed = b !== current();
      items().forEach(function (x) {
        x.setAttribute(attr, x === b ? "true" : "false");
        x.tabIndex = x === b ? 0 : -1;
      });
      sl.place(!(o && o.instant));
      if (changed && !(o && o.silent)) {
        el.dispatchEvent(new CustomEvent("change", { bubbles: true, detail: { value: valueOf(b), el: b } }));
        if (opts && typeof opts.onChange === "function") opts.onChange(valueOf(b), b);
      }
    }
    el.addEventListener("click", function (ev) {
      var b = ev.target.closest && ev.target.closest(".segmented-btn");
      if (!b || !el.contains(b) || b.disabled) return;
      select(b);
    });
    el.addEventListener("keydown", function (ev) {
      var k = ev.key;
      if (["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp", "Home", "End"].indexOf(k) < 0) return;
      var list = items().filter(function (b) { return !b.disabled; });
      if (!list.length) return;
      var i = list.indexOf(document.activeElement);
      if (i < 0) i = Math.max(0, list.indexOf(current()));
      if (k === "ArrowRight" || k === "ArrowDown") i = (i + 1) % list.length;
      else if (k === "ArrowLeft" || k === "ArrowUp") i = (i - 1 + list.length) % list.length;
      else if (k === "Home") i = 0;
      else i = list.length - 1;
      ev.preventDefault();
      list[i].focus();
      select(list[i]);
    });
    sync();
    var api = {
      select: select,
      value: function () { var c = current(); return c ? valueOf(c) : null; },
      refresh: function () { sync(); sl.refresh(); },
      el: el,
    };
    el._ecSeg = api;
    return api;
  };

  // ------------------------------------------------------------------ tabs (links)
  // <nav class="tabs"><a class="tab" data-tab="home" href="..." aria-current="page">..</a>..</nav>
  ui.tabs = function (el, activeSel) {
    if (!el) return null;
    var sl = slider(el, activeSel || '.tab[aria-current="page"]');
    return {
      setActive: function (key) {
        arr(el.querySelectorAll(".tab")).forEach(function (a) {
          if (a.getAttribute("data-tab") === key) a.setAttribute("aria-current", "page");
          else a.removeAttribute("aria-current");
        });
        sl.place(true);
      },
      refresh: sl.refresh,
    };
  };

  // ------------------------------------------------------------------ icon toggle
  function popIcon(btn) {
    if (reduced()) return;
    btn.classList.remove("is-popping");
    void btn.offsetWidth;
    btn.classList.add("is-popping");
    setTimeout(function () { btn.classList.remove("is-popping"); }, 340);
  }
  function setPressed(btn, on) {
    var was = btn.getAttribute("aria-pressed") === "true";
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    if (on && !was) popIcon(btn);
  }
  // iconToggle(btn | container): clicking flips aria-pressed (with the pop) and emits "change".
  // Page code that flips optimistically itself calls EC.ui.iconToggle.set(btn, on) instead.
  ui.iconToggle = function (target) {
    var list = !target ? [] : target.classList && target.classList.contains("icon-toggle") ? [target] : arr(target.querySelectorAll(".icon-toggle"));
    list.forEach(function (btn) {
      if (btn._ecIT) return;
      btn._ecIT = true;
      btn.addEventListener("click", function () {
        setPressed(btn, btn.getAttribute("aria-pressed") !== "true");
        btn.dispatchEvent(new CustomEvent("change", { bubbles: true, detail: { pressed: btn.getAttribute("aria-pressed") === "true" } }));
      });
    });
    return list;
  };
  ui.iconToggle.set = setPressed;

  // ------------------------------------------------------------------ disclosure
  // <details class="disclosure"><summary>..<i class="disclosure-chev"></i></summary><div class="disclosure-body">..</div></details>
  // Closing fades the content out (270ms) before `open` is removed. Works on every details.disclosure via one
  // delegated click handler, so markup that is re-rendered later needs no setup.
  function toggleDisclosure(d, want) {
    var isOpen = d.open && !d.classList.contains("is-closing");
    if (want === undefined) want = !isOpen;
    if (want === isOpen) return;
    clearTimeout(d._ecT);
    if (reduced()) {
      d.classList.remove("is-opening", "is-closing");
      d.open = want;
      return;
    }
    if (want) {
      d.classList.remove("is-closing");
      d.open = true;
      d.classList.add("is-opening");
      d._ecT = setTimeout(function () { d.classList.remove("is-opening"); }, 380);
    } else {
      d.classList.remove("is-opening");
      d.classList.add("is-closing");
      d._ecT = setTimeout(function () { d.open = false; d.classList.remove("is-closing"); }, 280);
    }
  }
  ui.disclosure = function (d, open) {
    if (d && open !== undefined) toggleDisclosure(d, !!open);
    return { toggle: function (v) { toggleDisclosure(d, v); }, el: d };
  };
  document.addEventListener("click", function (ev) {
    var s = ev.target.closest && ev.target.closest("summary");
    if (!s) return;
    var d = s.parentElement;
    if (!d || !d.classList || !d.classList.contains("disclosure") || d.tagName !== "DETAILS") return;
    if (ev.target.closest("a, button, input, select, textarea") && ev.target.closest("a, button, input, select, textarea") !== s) return;
    ev.preventDefault();
    toggleDisclosure(d);
  });

  // ------------------------------------------------------------------ menu / popover
  // The menu element needs class "menu" and role="menu"; items are .menu-item (role="menuitem").
  ui.menu = function (button, menuEl) {
    if (!button || !menuEl) return null;
    if (menuEl._ecMenu) return menuEl._ecMenu;
    var open = false;
    var id = menuEl.id || (menuEl.id = "menu-" + Math.random().toString(36).slice(2, 8));
    button.setAttribute("aria-haspopup", "menu");
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", id);
    function items() { return arr(menuEl.querySelectorAll('[role="menuitem"]')).filter(function (i) { return !i.disabled; }); }
    function onDoc(ev) { if (!menuEl.contains(ev.target) && !button.contains(ev.target)) close(false); }
    function onKey(ev) {
      if (ev.key === "Escape") { ev.preventDefault(); close(true); return; }
      if (ev.key === "Tab") { close(false); return; }
      var list = items();
      if (!list.length) return;
      var i = list.indexOf(document.activeElement);
      if (ev.key === "ArrowDown") { ev.preventDefault(); list[(i + 1) % list.length].focus(); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); list[(i - 1 + list.length) % list.length].focus(); }
      else if (ev.key === "Home") { ev.preventDefault(); list[0].focus(); }
      else if (ev.key === "End") { ev.preventDefault(); list[list.length - 1].focus(); }
    }
    function openMenu() {
      if (open) return;
      open = true;
      var r = button.getBoundingClientRect();
      menuEl.classList.toggle("menu-left", r.left + r.width / 2 < window.innerWidth / 2);
      menuEl.classList.add("is-open");
      button.setAttribute("aria-expanded", "true");
      document.addEventListener("mousedown", onDoc, true);
      document.addEventListener("touchstart", onDoc, true);
      document.addEventListener("keydown", onKey, true);
      var first = items()[0];
      if (first) first.focus({ preventScroll: true });
    }
    function close(refocus) {
      if (!open) return;
      open = false;
      menuEl.classList.remove("is-open");
      button.setAttribute("aria-expanded", "false");
      document.removeEventListener("mousedown", onDoc, true);
      document.removeEventListener("touchstart", onDoc, true);
      document.removeEventListener("keydown", onKey, true);
      if (refocus) button.focus({ preventScroll: true });
    }
    button.addEventListener("click", function () { if (open) close(true); else openMenu(); });
    button.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowDown" && !open) { ev.preventDefault(); openMenu(); }
    });
    menuEl.addEventListener("click", function (ev) {
      if (ev.target.closest('[role="menuitem"]')) close(false);
    });
    var api = { open: openMenu, close: close, toggle: function () { if (open) close(true); else openMenu(); }, isOpen: function () { return open; } };
    menuEl._ecMenu = api;
    return api;
  };

  // ------------------------------------------------------------------ markup helpers
  // Switch: a real checkbox with role="switch". `attrs` is trusted markup such as 'data-act="approve"'.
  ui.switchHtml = function (o) {
    o = o || {};
    var on = o.onLabel || "On", off = o.offLabel || "Off";
    return '<label class="switch"><input type="checkbox" role="switch"' + (o.checked ? " checked" : "") + (o.disabled ? " disabled" : "") +
      (o.attrs ? " " + o.attrs : "") + ' aria-label="' + esc(o.label || on) + '">' +
      '<span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>' +
      '<span class="switch-label" aria-hidden="true"><span class="sw-off">' + esc(off) + '</span><span class="sw-on">' + esc(on) + "</span></span></label>";
  };
  // Icon toggle: a raised icon button that becomes pressed (inset) when on.
  ui.iconToggleHtml = function (o) {
    o = o || {};
    return '<button class="icon-btn icon-toggle' + (o.cls ? " " + o.cls : "") + '" type="button"' + (o.attrs ? " " + o.attrs : "") +
      ' aria-pressed="' + (o.pressed ? "true" : "false") + '" aria-label="' + esc(o.label || "") + '" title="' + esc(o.title || o.label || "") + '">' +
      '<i data-lucide="' + esc(o.icon || "star") + '" aria-hidden="true"></i></button>';
  };
  // Status pill: kind = pass | fail | cant | human | running | neutral | priority | fixed | broke | same
  ui.pill = function (kind, text, o) {
    o = o || {};
    return '<span class="pill pill-' + esc(kind) + (o.pop ? " pop" : "") + (o.cls ? " " + o.cls : "") + '">' + esc(text) + "</span>";
  };

  // ------------------------------------------------------------------ checks: who decides, and browser steps
  // checkKind(check, o): "code" | "ai" | "browser" | "human".
  //   browser_count and ai_vision are both done in the real browser. "human" (You check) is only a legacy
  //   `manual` check, or o.handed = true when a result check was handed to a person at run time (passed null).
  ui.checkKind = function (c, o) {
    c = c || {};
    if (c.rule === "manual" || c.decided_by === "human") return "human";
    if (o && o.handed) return "human";
    if (c.rule === "browser_count" || c.rule === "ai_vision") return "browser";
    if (c.rule === "ai_judge" || c.decided_by === "ai") return "ai";
    return "code";
  };
  ui.checkTag = function (kind, cls) {
    var c = cls ? " " + cls : "";
    if (kind === "browser") return '<span class="pill pill-browser has-icon' + c + '" title="Real browser: used because this test needs a click or a look"><i data-lucide="globe" aria-hidden="true"></i>Real browser</span>';
    if (kind === "ai") return '<span class="pill pill-human' + c + '" title="AI: reads the page text and answers a yes/no question">AI</span>';
    if (kind === "human") return '<span class="pill pill-human' + c + '" title="You check: the last resort, only when we can\u2019t finish a check ourselves">You check</span>';
    return '<span class="pill pill-neutral' + c + '" title="Code: reads the page and decides, no clicks needed">Code</span>';
  };
  // One browser action in plain words (no capital letter at the start).
  function stepWords(s) {
    s = s || {};
    var out;
    if (s.goto != null) out = "opens " + s.goto;
    else if (s.click != null) {
      var t = String(s.click);
      if (/^css=/i.test(t)) {
        var sel = t.replace(/^css=/i, "");
        out = /menu/i.test(sel) ? "clicks the menu button" : "clicks " + sel;
      } else out = "clicks \u201c" + t.replace(/^text=/i, "") + "\u201d";
      if (s.optional) out += " (if there)";
    } else if (s.wait != null) out = "waits " + s.wait + " s";
    else if (s.scroll != null) out = s.scroll === "bottom" ? "scrolls to the bottom" : "scrolls";
    else out = "";
    return out;
  }
  // "Opens /products/solaris \u2192 clicks \u201cSand\u201d"  (empty string when there are no steps)
  ui.stepsText = function (steps) {
    if (!Array.isArray(steps) || !steps.length) return "";
    var s = steps.map(stepWords).filter(Boolean).join(" \u2192 ");
    return s.charAt(0).toUpperCase() + s.slice(1);
  };

  // ------------------------------------------------------------------ remembered project / run
  ui.remember = function (o) {
    o = o || {};
    if (o.projectId != null) {
      sset("ec.lastProject", o.projectId);
      if (o.projectName != null) sset("ec.lastProjectName", o.projectName);
      if (o.runId == null && sget("ec.lastRunProject") !== String(o.projectId)) {
        sset("ec.lastRun", null);
        sset("ec.lastRunProject", null);
      }
    }
    if (o.runId != null) {
      sset("ec.lastRun", o.runId);
      sset("ec.lastRunProject", o.projectId != null ? o.projectId : sget("ec.lastProject"));
    }
  };
  function forget() {
    ["ec.lastProject", "ec.lastProjectName", "ec.lastRun", "ec.lastRunProject"].forEach(function (k) { sset(k, null); });
  }

  // ------------------------------------------------------------------ top bar
  var TABS = [
    { key: "home", label: "My projects", short: "Projects", icon: "layout-grid" },
    { key: "tests", label: "Golden tests", short: "Tests", icon: "list-checks" },
    { key: "results", label: "Runs & results", short: "Results", icon: "activity" },
    { key: "compare", label: "Compare", short: "Compare", icon: "git-compare" },
  ];

  // opts: { page: "home" | "project" | "run", projectId, projectName, runId, runNumber, el }
  ui.topbar = function (opts) {
    var host = (opts && opts.el) || document.getElementById("topbar");
    if (!host) return null;
    var state = { page: "home", projectId: null, projectName: null, runId: null, runNumber: null };
    var desk = null, bar = null, menu = null;

    function assign(o) {
      ["page", "projectId", "projectName", "runId", "runNumber"].forEach(function (k) {
        if (o && o[k] !== undefined) state[k] = o[k];
      });
    }
    assign(opts);

    function email() {
      var s = EC.getSession && EC.getSession();
      return (s && s.user && s.user.email) || "";
    }
    function projectId() { return state.projectId != null ? String(state.projectId) : sget("ec.lastProject"); }
    function projectName() {
      if (state.projectName) return state.projectName;
      return state.projectId == null || String(state.projectId) === sget("ec.lastProject") ? sget("ec.lastProjectName") : null;
    }
    function runId() {
      if (state.runId != null) return String(state.runId);
      var p = projectId();
      var r = sget("ec.lastRun");
      if (!r) return null;
      var rp = sget("ec.lastRunProject");
      return !p || !rp || rp === String(p) ? r : null;
    }
    function activeKey() {
      if (state.page === "project") return "tests";
      if (state.page === "run") return location.hash === "#compare" ? "compare" : "results";
      return "home";
    }
    function hrefFor(key) {
      if (key === "home") return "/home.html";
      if (key === "tests") { var p = projectId(); return p ? "/project.html?id=" + encodeURIComponent(p) : null; }
      var r = runId();
      if (!r) return null;
      return "/run.html?id=" + encodeURIComponent(r) + (key === "compare" ? "#compare" : "");
    }
    function pageTitle() {
      if (state.page === "project") return state.projectName || "Golden tests";
      if (state.page === "run") return state.runNumber != null ? "Run " + state.runNumber : "Results";
      return "My projects";
    }

    function tabHtml(t, active, withIcon) {
      var href = hrefFor(t.key);
      var common = ' class="tab" data-tab="' + t.key + '"';
      var inner = (withIcon ? '<i data-lucide="' + t.icon + '" aria-hidden="true"></i><span>' + esc(t.short) + "</span>" : esc(t.label));
      if (!href) {
        return "<a" + common + ' role="link" aria-disabled="true" title="Open a project first">' + inner + "</a>";
      }
      return "<a" + common + ' href="' + esc(href) + '"' + (active ? ' aria-current="page"' : "") + (withIcon ? ' aria-label="' + esc(t.label) + '"' : "") + ">" + inner + "</a>";
    }

    function build() {
      var act = activeKey();
      var em = email();
      var letter = em ? em.trim().charAt(0).toUpperCase() : "?";
      host.innerHTML =
        '<a class="brand" href="/home.html" aria-label="Eval Co-pilot, my projects">' +
          '<span class="brand-tile"><i data-lucide="check" aria-hidden="true"></i></span>' +
          '<span class="brand-text"><span class="brand-name">Eval Co-pilot</span><span class="brand-sub">Website quality co-pilot</span></span></a>' +
        '<span class="topbar-title" id="topbar-title">' + esc(pageTitle()) + "</span>" +
        '<nav class="tabs" aria-label="Main">' + TABS.map(function (t) { return tabHtml(t, t.key === act, false); }).join("") + "</nav>" +
        '<div class="topbar-end">' +
          '<button class="btn btn-ghost btn-sm logout-btn" id="logout" type="button">Log out</button>' +
          '<div class="menu-wrap">' +
            '<button class="avatar" id="avatar" type="button" aria-label="Account menu" title="Account">' + esc(letter) + "</button>" +
            '<div class="menu" id="account-menu" role="menu" aria-label="Account">' +
              '<div class="menu-head" role="none"><span class="label-caps">Signed in as</span><span class="menu-email" id="user-email">' + esc(em) + "</span></div>" +
              '<button class="menu-item" id="menu-logout" type="button" role="menuitem"><i data-lucide="log-out" aria-hidden="true"></i>Log out</button>' +
            "</div></div></div>";

      var old = document.getElementById("tabbar");
      if (old) old.remove();
      bar = document.createElement("nav");
      bar.className = "tabbar";
      bar.id = "tabbar";
      bar.setAttribute("aria-label", "Main");
      bar.innerHTML = TABS.map(function (t) { return tabHtml(t, t.key === act, true); }).join("");
      document.body.appendChild(bar);
      document.body.classList.add("has-tabbar");

      icons();
      desk = ui.tabs(host.querySelector(".tabs"));
      ui.tabs(bar);
      bar.addEventListener("click", onTabClick);
      menu = ui.menu(host.querySelector("#avatar"), host.querySelector("#account-menu"));

      function out() { forget(); EC.logout(); }
      host.querySelector("#logout").addEventListener("click", out);
      host.querySelector("#menu-logout").addEventListener("click", out);
    }

    function setActive(key) {
      [host.querySelector(".tabs"), bar].forEach(function (c) {
        if (!c || !c._ecSlider) return;
        arr(c.querySelectorAll(".tab")).forEach(function (a) {
          if (a.getAttribute("data-tab") === key && a.getAttribute("aria-disabled") !== "true") a.setAttribute("aria-current", "page");
          else a.removeAttribute("aria-current");
        });
        c._ecSlider.place(true);
      });
    }

    // On the run page the Results / Compare tabs do not reload: they scroll and move the indicator.
    function onTabClick(ev) {
      var a = ev.target.closest && ev.target.closest(".tab");
      if (!a) return;
      if (a.getAttribute("aria-disabled") === "true") { ev.preventDefault(); return; }
      if (state.page !== "run") return;
      var key = a.getAttribute("data-tab");
      if (key !== "results" && key !== "compare") return;
      if (state.runId == null || String(runId()) !== String(state.runId)) return;
      ev.preventDefault();
      var smooth = reduced() ? "auto" : "smooth";
      if (key === "compare") {
        try { history.replaceState(null, "", location.pathname + location.search + "#compare"); } catch (e) { /* fine */ }
        var sec = document.getElementById("compare-section");
        if (sec && !sec.hidden) sec.scrollIntoView({ behavior: smooth, block: "start" });
      } else {
        try { history.replaceState(null, "", location.pathname + location.search); } catch (e) { /* fine */ }
        window.scrollTo({ top: 0, behavior: smooth });
      }
      setActive(key);
    }

    build();
    host.addEventListener("click", onTabClick);
    window.addEventListener("hashchange", function () { if (state.page === "run") setActive(activeKey()); });


    return {
      el: host,
      setActive: setActive,
      // update({projectId, projectName, runId, runNumber}) after the page has loaded its data
      update: function (o) {
        var wasOpen = menu && menu.isOpen();
        if (wasOpen) menu.close(false);
        assign(o);
        build();
      },
    };
  };
})();
