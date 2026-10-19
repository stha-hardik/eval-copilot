// Project screen: write golden pairs, tidy/suggest with the AI, approve them, then run.
// Uses window.EC from /js/api.js. All text from the server or the builder goes through EC.esc.
(function () {
  "use strict";
  if (!EC.requireLogin()) return;

  const esc = EC.esc;
  const projectId = EC.param("id");
  const page = document.getElementById("page");
  const GOAL = 10;
  const bar = EC.ui.topbar({ page: "project", projectId });

  // ---------- State ----------
  const state = {
    project: null,
    pairs: [],
    runs: [],
    filter: "all", // all | priority | suggested
    editors: new Map(), // key -> editor (unsaved drafts "d1", and in-place edits "e-<pairId>")
  };
  let draftSeq = 0;
  let newPairId = null; // pair to highlight after saving

  // ---------- Check rules ----------
  // who -> rules it can pick from. Rule -> wording.
  const WHO = {
    code: { label: "Code", rules: ["status_ok", "text_has", "text_absent", "count_equals", "min_results"] },
    ai: { label: "AI", rules: ["ai_judge"] },
    browser: { label: "Real browser", rules: ["browser_count", "ai_vision"] },
  };
  // who = the choice in "Who decides"; by = the decided_by the server stores; steps = shows the Steps box.
  // `manual` (a person checks) still exists on old pairs but is never offered: it is turned into a screenshot check.
  const RULE = {
    status_ok: { who: "code", by: "code", kind: "Page opens", label: "Nothing to fill in", ph: "" },
    text_has: { who: "code", by: "code", kind: "Shows text", label: "Words it should show", ph: "Solaris" },
    text_absent: { who: "code", by: "code", kind: "Doesn't show text", label: "Words it should not show", ph: "No results found" },
    count_equals: { who: "code", by: "code", kind: "Count is right", label: "What the count should be", ph: "item_count=1" },
    min_results: { who: "code", by: "code", kind: "At least N results", label: "Smallest number of results", ph: "3" },
    ai_judge: { who: "ai", by: "ai", kind: "AI question", label: "Question for the AI (about the page text)", ph: "Does the page show the battery runtime?" },
    browser_count: { who: "browser", by: "code", kind: "Count after real clicks", label: "What the cart count should be", ph: "item_count=1", steps: true },
    ai_vision: { who: "browser", by: "ai", kind: "AI looks at a screenshot", label: "What should the shopper see? (a yes/no question)", ph: "Is the menu open and showing the product links?", steps: true },
    manual: { who: "human", by: "human", kind: "You check", label: "What will you check?", ph: "Does the photo match the product?" },
  };

  function ruleOf(c) { return RULE[c.rule] || RULE.status_ok; }

  function checkText(c) {
    const e = (c.expected == null ? "" : String(c.expected)).trim();
    switch (c.rule) {
      case "status_ok": return "Page opens";
      case "text_has": return "Shows “" + e + "”";
      case "text_absent": return "Doesn't show “" + e + "”";
      case "count_equals": return "Count is right: " + e;
      case "min_results": return "At least " + e + (e === "1" ? " result" : " results");
      case "ai_judge": return e || "The AI answers a question about the page";
      case "browser_count": return "Count after real clicks: " + e;
      case "ai_vision": return "AI looks at a screenshot: " + e;
      case "manual": return "You check: " + e;
      default: return e || c.rule || "Check";
    }
  }

  function requestText(p) {
    const url = p.request_url || "/";
    if (p.method === "POST") {
      return /\/cart\//.test(url) ? "Adds to cart: " + url : "Sends data to " + url;
    }
    return "Opens " + url;
  }

  // ---------- Steps: one action per line in plain words <-> the steps JSON ----------
  // open /products/solaris | click Sand | click css=summary[aria-label=Menu] | click Menu (if there) | wait 2 | scroll to bottom
  function parseSteps(text) {
    const steps = [], errors = [];
    let n = 0;
    String(text || "").split(/\r?\n/).forEach((raw) => {
      n++;
      const line = raw.trim();
      if (!line) return;
      const m = /^(\S+)\s*(.*)$/.exec(line);
      const verb = m[1].toLowerCase();
      let rest = m[2].trim();
      const at = "Line " + n + ": ";
      if (verb === "open" || verb === "goto" || verb === "visit") {
        if (!rest) { errors.push(at + "say which page to open, like open /products/solaris."); return; }
        if (/\s/.test(rest)) { errors.push(at + "a page link has no spaces, like /products/solaris."); return; }
        steps.push({ goto: normPath(rest) });
      } else if (verb === "click" || verb === "press" || verb === "tap") {
        let optional = false;
        const om = /\s*\((?:if there|optional)\)\s*$/i.exec(rest);
        if (om) { optional = true; rest = rest.slice(0, om.index).trim(); }
        rest = rest.replace(/^["\u201c\u2018']+|["\u201d\u2019']+$/g, "").trim();
        if (!rest) { errors.push(at + "say what to click, like click Sand."); return; }
        let target;
        if (/^css=/i.test(rest)) {
          if (!rest.slice(4).trim()) { errors.push(at + "add a selector after css=."); return; }
          target = "css=" + rest.slice(4).trim();
        } else if (/^text=/i.test(rest)) {
          if (!rest.slice(5).trim()) { errors.push(at + "add the words to click after text=."); return; }
          target = "text=" + rest.slice(5).trim();
        } else target = "text=" + rest;
        const st = { click: target };
        if (optional) st.optional = true;
        steps.push(st);
      } else if (verb === "wait") {
        const wm = /^(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)?$/i.exec(rest);
        if (!wm) { errors.push(at + "say how many seconds, like wait 2."); return; }
        const secs = Number(wm[1]);
        if (!(secs > 0) || secs > 5) { errors.push(at + "we can wait between 0 and 5 seconds."); return; }
        steps.push({ wait: secs });
      } else if (verb === "scroll") {
        if (/^(?:to\s+)?(?:the\s+)?(?:bottom|end)$/i.test(rest)) steps.push({ scroll: "bottom" });
        else errors.push(at + "we can only scroll to the bottom: scroll to bottom.");
      } else {
        errors.push(at + "we don\u2019t know \u201c" + m[1] + "\u201d. Start with open, click, wait or scroll.");
      }
    });
    if (steps.length > 8) errors.push("That is " + steps.length + " actions. We can do up to 8.");
    return { steps, errors };
  }

  function stepsToLines(steps) {
    if (!Array.isArray(steps)) return "";
    return steps.map((s) => {
      s = s || {};
      if (s.goto != null) return "open " + s.goto;
      if (s.click != null) {
        const t = String(s.click);
        return "click " + (/^text=/i.test(t) ? t.slice(5) : t) + (s.optional ? " (if there)" : "");
      }
      if (s.wait != null) return "wait " + s.wait;
      if (s.scroll != null) return "scroll to bottom";
      return "";
    }).filter(Boolean).join("\n");
  }

  // ---------- Small helpers ----------
  function icons() { if (window.lucide) window.lucide.createIcons(); }
  function icon(name, cls) { return '<i data-lucide="' + name + '"' + (cls ? ' class="' + cls + '"' : "") + ' aria-hidden="true"></i>'; }
  function reducedMotion() { return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
  function errMsg(e, fallback) { return (e && e.message) || fallback || "That didn't work. Please try again."; }
  function hostOf(u) { try { return new URL(u).host; } catch (e) { return u || ""; } }
  function safeHref(u) { return /^https?:\/\//i.test(u || "") ? u : "#"; }
  function scrollToEl(el) {
    if (!el) return;
    el.scrollIntoView({ block: "nearest", behavior: reducedMotion() ? "auto" : "smooth" });
  }
  function normPath(v) {
    v = (v || "").trim();
    if (/^https?:\/\//i.test(v)) {
      try { const u = new URL(v); v = u.pathname + u.search; } catch (e) { /* keep as typed */ }
    }
    if (v && v[0] !== "/") v = "/" + v;
    return v;
  }
  function sortedPairs() {
    return state.pairs.slice().sort((a, b) =>
      (b.is_priority ? 1 : 0) - (a.is_priority ? 1 : 0) || (a.position - b.position));
  }
  function findPair(id) { return state.pairs.find((p) => String(p.id) === String(id)); }
  function counts() {
    const total = state.pairs.length;
    const approved = state.pairs.filter((p) => p.approved).length;
    return { total, approved, notApproved: total - approved };
  }

  // ---------- Page skeleton ----------
  function renderPage() {
    const pr = state.project;
    document.title = pr.name + " · Eval Co-pilot";
    page.innerHTML =
      '<div class="stack-lg">' +
        '<div class="page-head project-head enter" id="head">' + headHtml() + "</div>" +
        '<section class="stack enter" style="--i:1" id="sec-add" aria-labelledby="add-title">' + addCardHtml() +
          '<div class="suggest-row" id="sec-suggest">' +
            '<button class="btn btn-secondary" type="button" data-act="suggest" id="suggest-btn">' + icon("sparkles") + "Suggest pairs</button>" +
            '<p class="hint" id="suggest-help">The AI reads your home page like a sales expert and suggests pairs. You review them before they’re saved.</p>' +
          "</div>" +
          '<div class="stack" id="drafts"></div></section>' +
        '<section class="stack enter" style="--i:2" id="sec-list" aria-labelledby="list-title"></section>' +
        '<div class="enter" style="--i:3" id="sec-run"></div>' +
      "</div>";
    renderAddIntro();
    renderList(true);
    renderRun();
    setupVoice();
    icons();
  }

  function headHtml() {
    const pr = state.project;
    let past = "";
    if (state.runs.length) {
      past =
        '<div class="past-runs">' +
          '<label class="label" for="past-runs">Past runs</label>' +
          '<div class="row">' +
            '<select class="input" id="past-runs">' +
              state.runs.map((r) =>
                '<option value="' + esc(r.id) + '">Run ' + esc(r.run_number) + " · " + esc(r.passed) + " of " + esc(r.total) +
                " passed · " + esc(EC.fmtDate(r.started_at)) + "</option>").join("") +
            "</select>" +
            '<button class="btn btn-secondary" type="button" data-act="open-run">Open</button>' +
          "</div>" +
        "</div>";
    }
    return (
      '<div class="head-main">' +
        '<a class="back-link" href="/home.html">' + icon("arrow-left") + "Back to My projects</a>" +
        "<h1>" + esc(pr.name) + "</h1>" +
        '<a class="chip" href="' + esc(safeHref(pr.site_url)) + '" target="_blank" rel="noopener" title="' + esc(pr.site_url) + '">' +
          "<span>" + esc(hostOf(pr.site_url) || pr.site_url) + "</span>" + icon("external-link") + "</a>" +
        "<p class=\"muted\">Up to " + GOAL + " golden pairs. We try each one on your live site as a phone and as a laptop.</p>" +
      "</div>" +
      '<div class="head-side">' +
        '<div class="card count-card" id="count-card"></div>' + past +
      "</div>"
    );
  }

  function renderCount() {
    const el = document.getElementById("count-card");
    if (!el) return;
    const c = counts();
    const frac = Math.max(0, Math.min(1, c.total / GOAL));
    const label = c.total <= GOAL ? c.total + " of " + GOAL + " pairs" : c.total + " pairs";
    const bar = el.querySelector(".progress-fill");
    if (bar) {
      bar.style.setProperty("--p", frac.toFixed(4));
      el.querySelector("[data-count-label]").textContent = label;
      el.querySelector("[data-count-sub]").textContent = c.approved + " approved";
      el.querySelector(".progress").setAttribute("aria-valuenow", String(Math.min(c.total, GOAL)));
      return;
    }
    el.innerHTML =
      '<div class="count-top"><strong data-count-label>' + esc(label) + '</strong><span class="muted" data-count-sub>' + c.approved + " approved</span></div>" +
      '<div class="progress progress-sm count-bar" role="progressbar" aria-label="Golden pairs written" aria-valuemin="0" aria-valuemax="' + GOAL +
        '" aria-valuenow="' + Math.min(c.total, GOAL) + '"><div class="progress-fill" style="--p:' + frac.toFixed(4) + '"></div></div>';
  }

  // ---------- Add card ----------
  function addCardHtml() {
    return (
      '<div class="card stack" id="add-card">' +
        '<div class="stack-sm">' +
          '<div class="compose-title"><span class="icon-tile"><i data-lucide="pen-line" aria-hidden="true"></i></span>' +
          '<h2 class="section-title" id="add-title">Add a golden pair</h2></div>' +
          '<p class="muted" id="add-intro"></p>' +
        "</div>" +
        '<div id="add-banner"></div>' +
        '<div class="compose-grid">' +
          '<div class="compose-main">' +
            '<div class="two-col">' +
              taFieldHtml("user_does", "What does the user do?", "Searches for “Solaris” on the home page") +
              taFieldHtml("good_result", "What does a good result look like?", "Solaris appears, and the link opens the right product page") +
            "</div>" +
            '<div class="compose-actions">' +
              '<button class="btn btn-secondary" type="button" data-act="tidy" id="tidy-btn">' + icon("wand-sparkles") + "Tidy with AI</button>" +
              '<p class="hint voice-hint" id="voice-hint" hidden>Voice typing works in Chrome and Safari.</p>' +
            "</div>" +
          "</div>" +
          '<aside class="example" aria-label="Example pair">' +
            '<span class="label-caps example-title">' + icon("lightbulb") + "Example</span>" +
            '<p class="example-note">Write it the way you would tell a friend.</p>' +
            '<div class="example-card">' +
              '<span class="example-k">User does</span><span>Searches “Solaris”</span>' +
              '<span class="example-k">Good result</span><span>Solaris appears, and the link opens the right product page.</span>' +
            "</div>" +
          "</aside>" +
        "</div>" +
      "</div>"
    );
  }

  function taFieldHtml(name, label, placeholder) {
    return (
      '<div class="field" data-field="' + name + '">' +
        '<div class="field-top">' +
          '<label class="label" for="add-' + name + '">' + esc(label) + "</label>" +
          '<span class="listening" data-listen="' + name + '" hidden><span class="dot" aria-hidden="true"></span>Listening…</span>' +
        "</div>" +
        '<div class="ta-wrap">' +
          '<textarea class="input" id="add-' + name + '" rows="4" placeholder="' + esc(placeholder) + '"></textarea>' +
          '<button class="icon-btn icon-toggle is-outline mic" type="button" data-mic="' + name + '" aria-pressed="false" aria-label="Speak instead of typing" title="Speak instead of typing">' +
            icon("mic") + "</button>" +
        "</div>" +
        '<div class="error-msg" data-err="' + name + '" hidden></div>' +
      "</div>"
    );
  }

  function renderAddIntro() {
    const el = document.getElementById("add-intro");
    if (!el) return;
    el.textContent = state.pairs.length >= GOAL
      ? "You have " + GOAL + " pairs — that’s the goal. You can still add more if you need."
      : "Write down something a real customer does on your site, and what a good result looks like. Aim for " + GOAL + ".";
  }

  const addBanner = {
    show(msg) {
      document.getElementById("add-banner").innerHTML =
        '<div class="banner banner-error" role="alert"><span class="banner-icon">' + icon("circle-alert") + '</span><div class="banner-body"><span>' + esc(msg) + "</span></div></div>";
      icons();
    },
    clear() { const b = document.getElementById("add-banner"); if (b) b.innerHTML = ""; },
  };

  function addField(name) { return document.getElementById("add-" + name); }
  function setAddError(name, msg) {
    const ta = addField(name);
    const err = document.querySelector('#add-card [data-err="' + name + '"]');
    ta.classList.toggle("is-error", !!msg);
    if (msg) ta.setAttribute("aria-invalid", "true"); else ta.removeAttribute("aria-invalid");
    err.textContent = msg || "";
    err.hidden = !msg;
  }

  async function onTidy(btn) {
    stopVoice();
    addBanner.clear();
    const does = addField("user_does").value.trim();
    const good = addField("good_result").value.trim();
    if (!does) {
      setAddError("user_does", "Write what the user does, even roughly.");
      addField("user_does").focus();
      return;
    }
    setAddError("user_does", "");
    const rough = "User does: " + does + (good ? "\nGood result: " + good : "");
    await EC.busy(btn, async () => {
      try {
        const r = await EC.api("POST", "/api/pairs/tidy", { rough_text: rough, site_url: state.project.site_url });
        addField("user_does").value = "";
        addField("good_result").value = "";
        addEditor(r.pair, "builder", "tidy");
      } catch (e) {
        addBanner.show(e.status === 0 ? errMsg(e) : "The AI didn't answer. Please try again.");
      }
    }, "Tidying…");
  }

  async function onSuggest(btn) {
    addBanner.clear();
    const help = document.getElementById("suggest-help");
    const oldHelp = help.textContent;
    help.textContent = "Reading your site. This can take about 20 seconds.";
    await EC.busy(btn, async () => {
      try {
        const r = await EC.api("POST", "/api/projects/" + encodeURIComponent(projectId) + "/suggestions");
        const list = (r && r.pairs) || [];
        if (!list.length) {
          EC.toast("The AI had no suggestions this time. Try again, or write your own.", "info");
        } else {
          list.forEach((d, i) => addEditor(d, "suggested", "suggested", i === 0));
        }
      } catch (e) {
        addBanner.show(e.status === 0 ? errMsg(e) : "The AI didn't answer. Please try again.");
      }
    }, "Reading your site…");
    help.textContent = oldHelp;
  }

  // ---------- Voice typing ----------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let rec = null;

  function setupVoice() {
    if (SR) return;
    document.querySelectorAll(".mic").forEach((b) => b.remove());
    document.getElementById("voice-hint").hidden = false;
  }
  function setListening(name, on) {
    const btn = document.querySelector('[data-mic="' + name + '"]');
    const tag = document.querySelector('[data-listen="' + name + '"]');
    if (btn) EC.ui.iconToggle.set(btn, on);
    if (tag) tag.hidden = !on;
    const wrap = btn && btn.closest(".ta-wrap");
    if (wrap) wrap.classList.toggle("is-listening", on);
  }
  function stopVoice() {
    if (rec) { try { rec.stop(); } catch (e) { /* already stopped */ } }
  }
  function toggleVoice(name) {
    if (!SR) return;
    if (rec && rec.__name === name) { stopVoice(); return; }
    stopVoice();
    const ta = addField(name);
    const base = ta.value;
    const sep = base && !/\s$/.test(base) ? " " : "";
    const r = new SR();
    r.__name = name;
    r.continuous = false;
    r.interimResults = true;
    r.lang = navigator.language || "en-US";
    r.onresult = (ev) => {
      let t = "";
      for (let i = 0; i < ev.results.length; i++) t += ev.results[i][0].transcript;
      ta.value = base + sep + t.trim();
      setAddError(name, "");
    };
    r.onerror = (ev) => {
      if (ev && (ev.error === "not-allowed" || ev.error === "service-not-allowed")) {
        EC.toast("We couldn't use your microphone. Check that this site is allowed to use it.", "error");
      } else if (ev && ev.error === "no-speech") {
        EC.toast("We didn't hear anything. Try again.", "info");
      }
    };
    r.onend = () => { setListening(name, false); if (rec === r) rec = null; };
    rec = r;
    setListening(name, true);
    try { r.start(); } catch (e) { setListening(name, false); rec = null; }
  }

  // ---------- Editors (drafts and in-place edit) ----------
  function newEditor(draft, extra) {
    const d = draft || {};
    const locked = !!(extra && extra.locked);
    const reqPath = normPath(d.request_url);
    return Object.assign({
      draft: {
        user_does: d.user_does || "",
        good_result: d.good_result || "",
        request_url: d.request_url || "",
        method: d.method === "POST" ? "POST" : "GET",
        bodyText: d.request_body ? JSON.stringify(d.request_body, null, 2) : "",
        checks: (d.checks || []).map((c) => {
          // An old "you check" check becomes "AI looks at a screenshot" that opens the pair's page.
          if (!locked && (c.rule === "manual" || c.decided_by === "human")) {
            return { decided_by: "ai", rule: "ai_vision", expected: c.expected == null ? "" : String(c.expected),
              steps: null, stepsText: reqPath ? "open " + reqPath : "" };
          }
          const rule = c.rule || "status_ok";
          return {
            decided_by: (RULE[rule] || RULE.status_ok).by,
            rule: rule,
            expected: c.expected == null ? "" : String(c.expected),
            steps: Array.isArray(c.steps) ? c.steps : null,
            stepsText: stepsToLines(c.steps),
          };
        }),
      },
    }, extra);
  }

  function addEditor(draft, source, kind, keepScroll) {
    const key = "d" + (++draftSeq);
    const ed = newEditor(draft, { key, kind, source, pairId: null, locked: false });
    state.editors.set(key, ed);
    const holder = document.getElementById("drafts");
    const tmp = document.createElement("div");
    tmp.innerHTML = editorHtml(ed);
    const el = tmp.firstElementChild;
    el.classList.add("draft-in");
    holder.appendChild(el);
    icons();
    if (!keepScroll) scrollToEl(el);
  }

  function startEdit(pairId) {
    const p = findPair(pairId);
    if (!p) return;
    const key = "e-" + p.id;
    if (!state.editors.has(key)) {
      state.editors.set(key, newEditor(p, { key, kind: "edit", source: p.source, pairId: p.id, locked: !!p.has_results, position: p.position }));
    }
    renderList(false);
    const el = editorEl(key);
    if (el) { scrollToEl(el); const f = el.querySelector('[data-f="user_does"]'); if (f) f.focus({ preventScroll: true }); }
  }

  function editorEl(key) {
    return Array.prototype.find.call(document.querySelectorAll("[data-ed]"), (n) => n.dataset.ed === key) || null;
  }

  function refreshEditor(ed, focusKey) {
    const el = editorEl(ed.key);
    if (!el) return;
    const active = focusKey || (document.activeElement && document.activeElement.dataset && document.activeElement.dataset.f);
    const tmp = document.createElement("div");
    tmp.innerHTML = editorHtml(ed);
    el.replaceWith(tmp.firstElementChild);
    icons();
    if (active) {
      const n = Array.prototype.find.call(editorEl(ed.key).querySelectorAll("[data-f]"), (x) => x.dataset.f === active);
      if (n) n.focus();
    }
  }

  function selectOptions(items, current) {
    return items.map((it) =>
      '<option value="' + esc(it[0]) + '"' + (it[0] === current ? " selected" : "") + ">" + esc(it[1]) + "</option>").join("");
  }

  function checkRowHtml(ed, c, i) {
    const k = ed.key;
    const rule = ruleOf(c);
    const whoOpts = Object.keys(WHO).map((w) => [w, WHO[w].label]);
    const ruleOpts = (WHO[rule.who] || WHO.code).rules.map((r) => [r, RULE[r].kind]);
    const needsText = c.rule !== "status_ok";
    return (
      '<div class="check-ed" data-i="' + i + '">' +
      '<div class="check-row" data-i="' + i + '">' +
        '<div class="field">' +
          '<label class="label cr-label" for="' + esc(k) + "-c" + i + '-who">Who decides</label>' +
          '<select class="input" id="' + esc(k) + "-c" + i + '-who" data-f="c.' + i + '.who">' + selectOptions(whoOpts, rule.who) + "</select>" +
        "</div>" +
        '<div class="field">' +
          '<label class="label cr-label" for="' + esc(k) + "-c" + i + '-rule">Kind</label>' +
          '<select class="input" id="' + esc(k) + "-c" + i + '-rule" data-f="c.' + i + '.rule">' + selectOptions(ruleOpts, c.rule) + "</select>" +
        "</div>" +
        '<div class="field" data-field="c' + i + '">' +
          '<label class="label cr-label" for="' + esc(k) + "-c" + i + '-exp">' + esc(rule.label) + "</label>" +
          (needsText
            ? '<input class="input" type="text" id="' + esc(k) + "-c" + i + '-exp" data-f="c.' + i + '.expected" value="' + esc(c.expected) + '" placeholder="' + esc(rule.ph) + '" autocomplete="off">'
            : '<div class="cr-note muted small">Nothing to fill in. We check the page opens without an error.</div>') +
          '<div class="error-msg" data-err="c' + i + '" hidden></div>' +
        "</div>" +
        '<button class="icon-btn" type="button" data-act="rm-check" data-i="' + i + '" aria-label="Remove this check" title="Remove this check">' + icon("trash-2") + "</button>" +
      "</div>" +
      (rule.steps
        ? '<div class="field check-steps" data-field="s' + i + '">' +
            '<label class="label" for="' + esc(k) + "-c" + i + '-steps">Steps</label>' +
            '<textarea class="input" id="' + esc(k) + "-c" + i + '-steps" rows="3" data-f="c.' + i + '.steps" spellcheck="false" autocapitalize="off" autocomplete="off" placeholder="open /products/solaris&#10;click Sand">' + esc(c.stepsText) + "</textarea>" +
            '<div class="hint">One step per line (open, click, wait, scroll). The real browser follows them in order. It never pays, logs in or types into forms.</div>' +
            '<div class="error-msg steps-err" data-err="s' + i + '" hidden></div>' +
          "</div>"
        : "") +
      "</div>"
    );
  }

  // One check in a list: who decides, what it looks for, and (for a browser check) its steps in plain words.
  function checkItemHtml(c) {
    const st = EC.ui.stepsText(c.steps);
    return '<li class="chk">' + EC.ui.checkTag(EC.ui.checkKind(c), "who") +
      '<span class="chk-body"><span>' + esc(checkText(c)) + "</span>" +
      (st ? '<span class="chk-steps">' + esc(st) + "</span>" : "") + "</span></li>";
  }

  function lockedChecksHtml(ed) {
    return (
      '<ul class="check-list">' +
        ed.draft.checks.map(checkItemHtml).join("") +
      "</ul>" +
      '<p class="locked-note small muted">' + icon("lock") + "<span>Checks are locked after a run, so old results stay comparable.</span></p>"
    );
  }

  function editorHtml(ed) {
    const d = ed.draft, k = ed.key;
    const isEdit = ed.kind === "edit";
    let head;
    if (ed.kind === "tidy") {
      head = '<span class="pill pill-human has-icon">' + icon("wand-sparkles") + "Tidied by AI</span>" +
        '<h3 class="section-title">Tidied by AI — review it, then save</h3>';
    } else if (ed.kind === "suggested") {
      head = '<span class="pill pill-human has-icon">' + icon("sparkles") + "Suggested</span>" +
        '<h3 class="section-title">Suggested by the AI — review it, then save</h3>';
    } else {
      head = '<h3 class="section-title">Edit pair #' + esc(ed.position) + "</h3>";
    }
    const checksBody = ed.locked
      ? lockedChecksHtml(ed)
      : (d.checks.length
          ? '<div class="check-head" aria-hidden="true"><span>Who decides</span><span>Kind</span><span>What to look for</span><span></span></div>' +
            d.checks.map((c, i) => checkRowHtml(ed, c, i)).join("")
          : '<p class="small muted">No checks yet. Add one so we can tell a pass from a fail.</p>') +
        '<div class="error-msg" data-err="checks" hidden></div>' +
        '<div><button class="btn btn-secondary btn-sm" type="button" data-act="add-check">' + icon("plus") + "Add a check</button></div>";

    return (
      '<div class="card draft stack" data-ed="' + esc(k) + '">' +
        '<div class="draft-head row">' + head + "</div>" +
        '<div class="two-col">' +
          '<div class="field" data-field="user_does">' +
            '<label class="label" for="' + esc(k) + '-user_does">What does the user do?</label>' +
            '<textarea class="input" id="' + esc(k) + '-user_does" rows="3" data-f="user_does">' + esc(d.user_does) + "</textarea>" +
            '<div class="error-msg" data-err="user_does" hidden></div>' +
          "</div>" +
          '<div class="field" data-field="good_result">' +
            '<label class="label" for="' + esc(k) + '-good_result">What does a good result look like?</label>' +
            '<textarea class="input" id="' + esc(k) + '-good_result" rows="3" data-f="good_result">' + esc(d.good_result) + "</textarea>" +
            '<div class="error-msg" data-err="good_result" hidden></div>' +
          "</div>" +
        "</div>" +
        '<div class="req-grid">' +
          '<div class="field" data-field="request_url">' +
            '<label class="label" for="' + esc(k) + '-url">Page to open on your site</label>' +
            '<input class="input" type="text" id="' + esc(k) + '-url" data-f="request_url" value="' + esc(d.request_url) + '" placeholder="/search?q=Solaris" autocomplete="off" autocapitalize="off" spellcheck="false">' +
            '<div class="hint">Starts with /. We add your site’s address for you.</div>' +
            '<div class="error-msg" data-err="request_url" hidden></div>' +
          "</div>" +
          '<div class="field">' +
            '<label class="label" for="' + esc(k) + '-method">How we reach it</label>' +
            '<select class="input" id="' + esc(k) + '-method" data-f="method">' +
              selectOptions([["GET", "Open page"], ["POST", "Send data"]], d.method) + "</select>" +
          "</div>" +
        "</div>" +
        (d.method === "POST"
          ? '<div class="field" data-field="body">' +
              '<label class="label" for="' + esc(k) + '-body">Data to send (as JSON)</label>' +
              '<textarea class="input mono" id="' + esc(k) + '-body" rows="4" data-f="bodyText" spellcheck="false" placeholder=\'{"id": 123, "quantity": 1}\'>' + esc(d.bodyText) + "</textarea>" +
              '<div class="error-msg" data-err="body" hidden></div>' +
            "</div>"
          : "") +
        '<div class="stack-sm checks-block">' +
          '<div class="stack-sm"><h4 class="section-title">Checks</h4>' +
          '<p class="small muted">Each check says what to look for. We use the simplest way to check it: code reading the page, the AI on the page text, or a real browser, only when a test needs a click or a look. If we can\u2019t finish one, we ask you and say why.</p></div>' +
          checksBody +
        "</div>" +
        '<div data-ed-banner>' + edBannerHtml(ed) + "</div>" +
        '<div class="row draft-actions">' +
          '<button class="btn btn-secondary" type="button" data-act="save-ed">' + (isEdit ? "Save changes" : "Save pair") + "</button>" +
          '<button class="btn btn-ghost" type="button" data-act="discard-ed">' + (isEdit ? "Cancel" : "Discard") + "</button>" +
        "</div>" +
      "</div>"
    );
  }

  function edBannerHtml(ed) {
    return ed.banner
      ? '<div class="banner banner-error" role="alert"><span class="banner-icon">' + icon("circle-alert") + '</span><div class="banner-body"><span>' + esc(ed.banner) + "</span></div></div>"
      : "";
  }
  function setEdBanner(ed, msg) {
    ed.banner = msg || "";
    const root = editorEl(ed.key);
    const slot = root && root.querySelector("[data-ed-banner]");
    if (!slot) return;
    slot.innerHTML = edBannerHtml(ed);
    icons();
    if (msg) scrollToEl(slot);
  }

  function setEdError(ed, key, msg) {
    const root = editorEl(ed.key);
    if (!root) return;
    const err = Array.prototype.find.call(root.querySelectorAll("[data-err]"), (n) => n.dataset.err === key);
    const wrap = Array.prototype.find.call(root.querySelectorAll("[data-field]"), (n) => n.dataset.field === key);
    if (wrap) {
      wrap.querySelectorAll(".input").forEach((inp) => {
        if (inp.tagName === "SELECT") return;
        inp.classList.toggle("is-error", !!msg);
        if (msg) inp.setAttribute("aria-invalid", "true"); else inp.removeAttribute("aria-invalid");
      });
    }
    if (err) { err.textContent = msg || ""; err.hidden = !msg; }
  }

  function checkBody(ed) {
    const d = ed.draft;
    if (d.method !== "POST") return { ok: true, value: null };
    const t = d.bodyText.trim();
    if (!t) return { ok: false, msg: "Add the data to send, or switch to “Open page”." };
    try { return { ok: true, value: JSON.parse(t) }; } catch (e) {
      return { ok: false, msg: "This isn’t valid JSON yet. Check the brackets and quotes." };
    }
  }

  function validateEditor(ed) {
    const d = ed.draft;
    let ok = true, first = null;
    const fail = (key, msg) => { setEdError(ed, key, msg); if (msg) { ok = false; if (!first) first = key; } };
    fail("user_does", d.user_does.trim() ? "" : "Write what the user does.");
    fail("good_result", d.good_result.trim() ? "" : "Write what a good result looks like.");
    fail("request_url", normPath(d.request_url) ? "" : "Add the page to open, like /search?q=Solaris.");
    const b = checkBody(ed);
    fail("body", b.ok ? "" : b.msg);
    if (!ed.locked) {
      fail("checks", d.checks.length ? "" : "Add at least one check so we can tell a pass from a fail.");
      d.checks.forEach((c, i) => {
        fail("c" + i, c.rule === "status_ok" || String(c.expected).trim() ? "" : "Fill this in.");
        if (ruleOf(c).steps) fail("s" + i, parseSteps(c.stepsText).errors.join("\n"));
      });
    }
    if (!ok) {
      const root = editorEl(ed.key);
      const wrap = root && Array.prototype.find.call(root.querySelectorAll("[data-field],[data-err]"), (n) =>
        (n.dataset.field === first || n.dataset.err === first));
      const inp = wrap && wrap.querySelector(".input");
      if (inp) inp.focus(); else if (wrap) scrollToEl(wrap);
    }
    return { ok, body: b.value };
  }

  function editorPayload(ed, body) {
    const d = ed.draft;
    const out = {
      user_does: d.user_does.trim(),
      good_result: d.good_result.trim(),
      request_url: normPath(d.request_url),
      method: d.method,
      request_body: d.method === "POST" ? body : null,
    };
    if (!ed.locked) {
      out.checks = d.checks.map((c) => ({
        decided_by: ruleOf(c).by,
        rule: c.rule,
        expected: c.rule === "status_ok" ? null : String(c.expected).trim(),
        steps: ruleOf(c).steps ? parseSteps(c.stepsText).steps : null,
      }));
    }
    return out;
  }

  async function saveEditor(ed, btn) {
    setEdBanner(ed, "");
    const v = validateEditor(ed);
    if (!v.ok) return;
    const payload = editorPayload(ed, v.body);
    await EC.busy(btn, async () => {
      try {
        if (ed.kind === "edit") {
          const r = await EC.api("PATCH", "/api/pairs/" + encodeURIComponent(ed.pairId), payload);
          const idx = state.pairs.findIndex((p) => String(p.id) === String(ed.pairId));
          if (idx >= 0 && r && r.pair) state.pairs[idx] = r.pair;
          state.editors.delete(ed.key);
          renderList(false);
          renderRun();
          EC.toast("Changes saved.", "success");
        } else {
          const body = Object.assign({}, payload, { source: ed.source, approved: false });
          const r = await EC.api("POST", "/api/projects/" + encodeURIComponent(projectId) + "/pairs", body);
          state.pairs.push(r.pair);
          state.editors.delete(ed.key);
          const el = editorEl(ed.key);
          if (el) el.remove();
          newPairId = r.pair.id;
          state.filter = "all";
          renderAddIntro();
          renderList(false);
          renderRun();
          EC.toast("Pair saved. Approve it when it looks right.", "success");
          scrollToEl(document.querySelector('[data-pair="' + String(newPairId).replace(/"/g, "") + '"]'));
        }
      } catch (e) {
        setEdBanner(ed, errMsg(e));
      }
    }, "Saving…");
  }

  function discardEditor(ed) {
    state.editors.delete(ed.key);
    if (ed.kind === "edit") {
      renderList(false);
    } else {
      const el = editorEl(ed.key);
      if (el) el.remove();
    }
  }

  // ---------- Pairs list ----------
  function kindChips(p) {
    const seen = [];
    (p.checks || []).forEach((c) => { const k = EC.ui.checkKind(c); if (seen.indexOf(k) < 0) seen.push(k); });
    return ["code", "ai", "browser", "human"].filter((k) => seen.indexOf(k) >= 0).map((k) => EC.ui.checkTag(k)).join("");
  }

  function pillsHtml(p) {
    let h = "";
    if (p.is_priority) h += '<span class="pill pill-priority">Priority</span>';
    if (p.source === "suggested") h += '<span class="pill pill-human has-icon">' + icon("sparkles") + "Suggested</span>";
    return h + kindChips(p);
  }

  function pairCardHtml(p, idx, animate) {
    const ed = state.editors.get("e-" + p.id);
    if (ed) return "<li>" + editorHtml(ed) + "</li>";
    const isNew = p.id === newPairId;
    const checks = (p.checks || []).map(checkItemHtml).join("");
    const liCls = animate && !isNew ? ' class="enter" style="--i:' + idx + '"' : "";
    return (
      "<li" + liCls + ">" +
      '<article class="card pair' + (isNew ? " is-new" : "") + '" data-pair="' + esc(p.id) + '">' +
        '<div class="pair-top">' +
          '<span class="pair-num">#' + esc(p.position) + "</span>" +
          '<div class="pair-pills">' + pillsHtml(p) + "</div>" +
          '<div class="pair-actions">' +
            EC.ui.switchHtml({ checked: p.approved, onLabel: "Approved", offLabel: "Not approved", label: "Approved", attrs: 'data-act="approve"' }) +
            EC.ui.iconToggleHtml({ icon: "star", pressed: p.is_priority, label: "Priority", title: "Mark as priority", attrs: 'data-act="priority"' }) +
            '<button class="icon-btn" type="button" data-act="edit" aria-label="Edit pair ' + esc(p.position) + '" title="Edit">' + icon("pencil") + "</button>" +
          "</div>" +
        "</div>" +
        '<div class="pair-trays">' +
          '<div class="tray"><span class="tray-label">User does</span><p>' + esc(p.user_does) + "</p></div>" +
          '<div class="tray"><span class="tray-label">Good result</span><p>' + esc(p.good_result) + "</p></div>" +
        "</div>" +
        '<div class="pair-checks"><span class="tray-label">Checks</span>' +
          (checks ? '<ul class="check-list">' + checks + "</ul>" : '<p class="small muted">No checks yet.</p>') +
          '<p class="small muted pair-request">' + esc(requestText(p)) + "</p>" +
        "</div>" +
      "</article></li>"
    );
  }

  function filteredPairs() {
    const all = sortedPairs();
    if (state.filter === "priority") return all.filter((p) => p.is_priority);
    if (state.filter === "suggested") return all.filter((p) => p.source === "suggested");
    return all;
  }

  // The segmented control is created once and kept, so its indicator can slide between options.
  const FILTERS = [["all", "All"], ["priority", "Priority"], ["suggested", "Suggested"]];
  function filterCounts() {
    return {
      all: state.pairs.length,
      priority: state.pairs.filter((p) => p.is_priority).length,
      suggested: state.pairs.filter((p) => p.source === "suggested").length,
    };
  }
  function updateChips() {
    const slot = document.getElementById("filter-slot");
    if (!slot) return;
    if (state.pairs.length <= 1) { slot.innerHTML = ""; return; }
    const n = filterCounts();
    let seg = slot.querySelector(".filter-chips");
    if (!seg) {
      slot.innerHTML = '<div class="segmented filter-chips" role="group" aria-label="Show">' +
        FILTERS.map((f) => '<button class="segmented-btn" type="button" data-value="' + f[0] + '" aria-pressed="' + (state.filter === f[0] ? "true" : "false") + '"></button>').join("") + "</div>";
      seg = slot.querySelector(".filter-chips");
      EC.ui.segmented(seg);
      seg.addEventListener("change", (ev) => { state.filter = ev.detail.value; renderList(false); });
    }
    FILTERS.forEach((f) => {
      const b = seg.querySelector('[data-value="' + f[0] + '"]');
      if (b) b.textContent = f[1] + " (" + n[f[0]] + ")";
    });
    seg._ecSeg.select(state.filter, { silent: true });
    seg._ecSeg.refresh();
  }

  function renderList(animate) {
    const sec = document.getElementById("sec-list");
    if (!sec) return;
    const c = counts();
    const anyPriority = state.pairs.some((p) => p.is_priority);
    if (state.filter === "priority" && !anyPriority) state.filter = "all";
    if (state.filter === "suggested" && !state.pairs.some((p) => p.source === "suggested")) state.filter = "all";
    if (!sec.querySelector("#list-body")) {
      sec.innerHTML = '<div class="list-head"><h2 class="section-title" id="list-title"></h2><div class="filter-slot" id="filter-slot"></div></div>' +
        '<p class="small muted order-note" id="order-note" hidden>Priority pairs are listed first.</p><div id="list-body"></div>';
    }
    document.getElementById("list-title").innerHTML = "Your golden pairs" +
      (c.total ? '<span class="count" id="counter">(' + (c.total <= GOAL ? c.total + " of " + GOAL : c.total) + ")</span>" : "");
    document.getElementById("order-note").hidden = !(anyPriority && c.total > 1);
    updateChips();
    let body;
    if (!c.total) {
      body = '<div class="card empty">' + '<span class="empty-icon">' + icon("list-checks") + "</span>" +
        '<p class="empty-title">No pairs yet</p><p class="muted">Write your first one above.</p></div>';
    } else {
      const list = filteredPairs();
      body = list.length
        ? '<ul class="pair-list">' + list.map((p, i) => pairCardHtml(p, i + 1, animate)).join("") + "</ul>"
        : '<p class="filter-empty">No pairs match this filter.</p>';
    }
    document.getElementById("list-body").innerHTML = body;
    icons();
    newPairId = null;
    renderCount();
  }

  // Keep counts, filter chips and the run bar in step after a toggle (without re-drawing the cards).
  function refreshMeta() {
    renderCount();
    renderRun();
    updateChips();
  }

  async function togglePair(id, field, value, focusAct) {
    const p = findPair(id);
    if (!p) return;
    const old = p[field];
    p[field] = value;
    const card = () => Array.prototype.find.call(document.querySelectorAll("[data-pair]"), (n) => n.dataset.pair === String(id));
    if (field === "approved") {
      refreshMeta();
    } else {
      // priority: flip the star at once, then re-sort after the 220ms feedback
      const star = card() && card().querySelector('[data-act="priority"]');
      if (star) EC.ui.iconToggle.set(star, value);
      refreshMeta();
    }
    const t0 = Date.now();
    try {
      await EC.api("PATCH", "/api/pairs/" + encodeURIComponent(id), { [field]: value });
      if (field === "is_priority") {
        // let the star's pop finish (about 300ms) before the list re-sorts
        const wait = reducedMotion() ? 0 : Math.max(0, 300 - (Date.now() - t0));
        if (wait) await new Promise((r) => setTimeout(r, wait));
        renderList(false);
        restoreFocus(id, focusAct);
      }
    } catch (e) {
      p[field] = old;
      if (field === "approved") {
        const sw = card() && card().querySelector('[data-act="approve"]');
        if (sw) sw.checked = !!old;
        refreshMeta();
      } else {
        renderList(false);
        renderRun();
        restoreFocus(id, focusAct);
      }
      EC.toast(errMsg(e, "We couldn't save that change. Please try again."), "error");
    }
  }

  function restoreFocus(id, act) {
    const card = Array.prototype.find.call(document.querySelectorAll("[data-pair]"), (n) => n.dataset.pair === String(id));
    const el = card && card.querySelector('[data-act="' + act + '"]');
    if (el) el.focus({ preventScroll: true });
  }

  // ---------- Run section ----------
  function renderRun() {
    const sec = document.getElementById("sec-run");
    if (!sec) return;
    const c = counts();
    const can = c.approved > 0;
    let note = "";
    if (!can) note = "Approve at least one pair to run.";
    else if (c.notApproved > 0) {
      note = c.notApproved === 1
        ? "1 pair isn’t approved, so it won’t run."
        : c.notApproved + " pairs aren’t approved, so they won’t run.";
    }
    const title = can ? c.approved + (c.approved === 1 ? " pair ready" : " pairs ready") : "No pairs ready yet";
    const busy = sec.querySelector("#run-btn[aria-busy='true']");
    if (busy) return; // never rebuild a button that is mid-click
    sec.innerHTML =
      '<div class="run-dock">' +
        '<div class="run-text">' +
          "<strong>" + esc(title) + "</strong>" +
          '<p class="run-help">Tests every approved pair on a phone and a laptop. About 10–30 seconds per pair, up to a minute if it needs a real browser.</p>' +
          (note ? '<p class="run-note" id="run-note">' + esc(note) + "</p>" : "") +
        "</div>" +
        '<button class="btn btn-primary" type="button" data-act="run-all" id="run-btn"' + (can ? "" : " disabled") +
          (can ? "" : ' aria-describedby="run-note"') + ">" + icon("play") + '<span class="lbl-full">Run all approved pairs</span><span class="lbl-short">Run all</span>' + (can ? " (" + c.approved + ")" : "") + "</button>" +
      "</div>";
    icons();
  }

  async function onRunAll(btn) {
    await EC.busy(btn, async () => {
      try {
        const r = await EC.api("POST", "/api/projects/" + encodeURIComponent(projectId) + "/runs", { kind: "full" });
        const id = r && r.run && r.run.id;
        if (!id) throw new Error("We couldn't start the run. Please try again.");
        try { sessionStorage.setItem("ec.run." + id + ".pairs", JSON.stringify(r.pair_ids || [])); } catch (e) {}
        btn.disabled = true;
        location.href = "/run.html?id=" + encodeURIComponent(id) + "&start=1";
        await new Promise(() => {}); // stay greyed out while the browser navigates
      } catch (e) {
        EC.toast(errMsg(e, "We couldn't start the run. Please try again."), "error");
      }
    }, "Starting…");
  }

  // ---------- Events ----------
  function edFromEvent(t) {
    const root = t.closest("[data-ed]");
    return root ? state.editors.get(root.dataset.ed) : null;
  }

  page.addEventListener("click", (ev) => {
    const mic = ev.target.closest("[data-mic]");
    if (mic) { toggleVoice(mic.dataset.mic); return; }
    const t = ev.target.closest("[data-act]");
    if (!t) return;
    const act = t.dataset.act;
    const card = t.closest("[data-pair]");
    const ed = edFromEvent(t);
    switch (act) {
      case "tidy": onTidy(t); break;
      case "suggest": onSuggest(t); break;
      case "run-all": onRunAll(t); break;
      case "open-run": {
        const sel = document.getElementById("past-runs");
        if (sel && sel.value) location.href = "/run.html?id=" + encodeURIComponent(sel.value);
        break;
      }
      case "edit": if (card) startEdit(card.dataset.pair); break;
      case "priority": if (card) togglePair(card.dataset.pair, "is_priority", !findPair(card.dataset.pair).is_priority, "priority"); break;
      case "add-check":
        if (ed) { ed.draft.checks.push({ decided_by: "code", rule: "text_has", expected: "", steps: null, stepsText: "" }); refreshEditor(ed); focusLastCheck(ed); }
        break;
      case "rm-check":
        if (ed) { ed.draft.checks.splice(Number(t.dataset.i), 1); refreshEditor(ed, "none"); const b = editorEl(ed.key).querySelector('[data-act="add-check"]'); if (b) b.focus({ preventScroll: true }); }
        break;
      case "save-ed": if (ed) saveEditor(ed, t); break;
      case "discard-ed": if (ed) discardEditor(ed); break;
      default: break;
    }
  });

  function focusLastCheck(ed) {
    const root = editorEl(ed.key);
    const rows = root.querySelectorAll(".check-row");
    const last = rows[rows.length - 1];
    const f = last && last.querySelector('[data-f$=".expected"], [data-f$=".rule"]');
    if (f) f.focus({ preventScroll: false });
  }

  page.addEventListener("change", (ev) => {
    const t = ev.target;
    if (t.matches && t.matches('input[data-act="approve"]')) {
      const card = t.closest("[data-pair]");
      if (card) togglePair(card.dataset.pair, "approved", t.checked, "approve");
      return;
    }
    const ed = edFromEvent(t);
    const f = t.dataset && t.dataset.f;
    if (!ed || !f) return;
    if (f === "method") {
      ed.draft.method = t.value;
      refreshEditor(ed, "method");
      return;
    }
    const m = /^c\.(\d+)\.(who|rule)$/.exec(f);
    if (m) {
      const c = ed.draft.checks[Number(m[1])];
      if (!c) return;
      if (m[2] === "who") {
        c.rule = WHO[t.value].rules[0];
        c.decided_by = RULE[c.rule].by;
        c.expected = "";
      } else {
        const wasBrowser = ruleOf(c).who === "browser";
        c.rule = t.value;
        c.decided_by = RULE[c.rule].by;
        if (c.rule === "status_ok" || (wasBrowser && RULE[c.rule].who === "browser")) c.expected = "";
      }
      refreshEditor(ed, f);
    }
  });

  page.addEventListener("input", (ev) => {
    const t = ev.target;
    const ed = edFromEvent(t);
    const f = t.dataset && t.dataset.f;
    if (ed && f) {
      if (f === "user_does" || f === "good_result" || f === "request_url" || f === "bodyText") {
        ed.draft[f] = t.value;
        setEdError(ed, f === "bodyText" ? "body" : f, "");
      } else {
        const m = /^c\.(\d+)\.(expected|steps)$/.exec(f);
        if (m && ed.draft.checks[Number(m[1])]) {
          if (m[2] === "steps") {
            ed.draft.checks[Number(m[1])].stepsText = t.value;
            setEdError(ed, "s" + m[1], "");
          } else {
            ed.draft.checks[Number(m[1])].expected = t.value;
            setEdError(ed, "c" + m[1], "");
          }
        }
      }
      return;
    }
    if (t.id === "add-user_does") setAddError("user_does", "");
  });

  page.addEventListener("focusout", (ev) => {
    const t = ev.target;
    const sm = t.dataset && /^c\.(\d+)\.steps$/.exec(t.dataset.f || "");
    if (sm) {
      const sed = edFromEvent(t);
      if (sed && t.value.trim()) setEdError(sed, "s" + sm[1], parseSteps(t.value).errors.join("\n"));
    }
    if (t.dataset && t.dataset.f === "bodyText") {
      const ed = edFromEvent(t);
      if (ed && t.value.trim()) {
        const b = checkBody(ed);
        setEdError(ed, "body", b.ok ? "" : b.msg);
      }
    }
  });

  // ---------- Load ----------
  function renderNotFound(msg) {
    page.innerHTML =
      '<div class="card empty enter">' +
        '<span class="empty-icon">' + icon("search-x") + "</span>" +
        '<h2 class="empty-title">' + esc(msg) + "</h2>" +
        '<a class="btn btn-secondary" href="/home.html">Back to My projects</a>' +
      "</div>";
    icons();
  }

  function renderLoadError(e) {
    page.innerHTML =
      '<div class="banner banner-error enter" role="alert"><span class="banner-icon">' + icon("circle-alert") + "</span>" +
      '<div class="banner-body"><span>' + esc(errMsg(e, "We couldn’t load this project.")) + "</span></div>" +
      '<button class="btn btn-secondary btn-sm" id="retry" type="button">Try again</button></div>';
    icons();
    document.getElementById("retry").addEventListener("click", () => {
      page.innerHTML = '<div class="stack-lg" aria-busy="true"><div class="skeleton" style="height:120px;border-radius:24px"></div><div class="skeleton skeleton-card" style="height:320px"></div></div>';
      load();
    });
  }

  async function load() {
    if (!projectId) { renderNotFound("We couldn’t find this project."); return; }
    try {
      const data = await EC.api("GET", "/api/projects/" + encodeURIComponent(projectId));
      state.project = data.project;
      state.pairs = data.pairs || [];
      state.runs = data.runs || [];
      EC.ui.remember({ projectId: state.project.id != null ? state.project.id : projectId, projectName: state.project.name });
      bar.update({ projectId: state.project.id != null ? state.project.id : projectId, projectName: state.project.name });
      renderPage();
    } catch (e) {
      if (e.status === 404) renderNotFound("We couldn’t find this project.");
      else renderLoadError(e);
    }
  }

  load();
})();
