// Results screen: /run.html?id=<run id>[&start=1]
// Live mode (start=1) tests one pair at a time and fills the results feed as answers arrive.
(function () {
  "use strict";

  const e = EC.esc;
  const RUN_ID = EC.param("id");
  const LIVE = EC.param("start") === "1";
  const KEY_CLOSED = "ec.run.keyClosed";

  // ---------- state ----------
  const S = {
    run: null, project: null,
    rows: [], points: [], changed: [], earlier: [],
    finished: false, running: false,
    liveIds: [],            // pair ids in the order they run (live mode)
    meta: {},               // pair_id -> {position, user_does, is_priority}
    pairState: {},          // pair_id -> waiting | testing | failed | done
    expanded: {},           // result_id -> true when "More" is open
    detailsOpen: {},        // result_id -> true/false once the builder toggled the checks
    picks: new Set(),       // pair ids ticked for "Re-run changed"
    otherPair: null,        // {id, user_does} once an "other change" was approved
    draft: null,            // proposed pair from "Turn into a check"
    note: "",
    compareDone: false,
    prog: null,             // live progress {text, done, total, busy}
    changedShown: false,    // the "Good now?" panel animates in once
  };

  const $ = (id) => document.getElementById(id);
  let bar = null; // the shared top bar (EC.ui.topbar)

  // ---------- small helpers ----------
  function icons() { if (window.lucide && window.lucide.createIcons) window.lucide.createIcons(); }
  function ic(name) { return '<i data-lucide="' + name + '" aria-hidden="true"></i>'; }
  function setHtml(id, html) { const el = $(id); if (el) el.innerHTML = html; icons(); }
  function storeGet(k) { try { return localStorage.getItem(k); } catch (err) { return null; } }
  function storeSet(k, v) { try { localStorage.setItem(k, v); } catch (err) { /* fine */ } }
  function sessGet(k) { try { return sessionStorage.getItem(k); } catch (err) { return null; } }
  function sessSet(k, v) { try { sessionStorage.setItem(k, v); } catch (err) { /* fine */ } }
  function plural(n, one, many) { return n === 1 ? one : many; }
  function hostOf(url) { try { return new URL(url).host; } catch (err) { return url || ""; } }
  function num(p) { return p == null ? "#" : "#" + p; }

  function outcomePill(o, pop) {
    if (o === "pass") return EC.ui.pill("pass", "Pass", { pop: pop });
    if (o === "fail") return EC.ui.pill("fail", "Fail", { pop: pop });
    if (o === "cant_test") return EC.ui.pill("cant", "Can’t test", { pop: pop });
    return EC.ui.pill("neutral", "Not tested", { pop: pop });
  }
  function deviceLabel(d) { return d === "phone" ? "Phone" : "Laptop"; }
  function deviceIcon(d) { return d === "phone" ? "smartphone" : "laptop"; }
  
  // ---------- plain-words check text ----------
  function ruleText(c) {
    const x = c.expected == null ? "" : String(c.expected);
    switch (c.rule) {
      case "status_ok": return "Page opens";
      case "text_has": return "Shows “" + x + "”";
      case "text_absent": return "Doesn’t show “" + x + "”";
      case "count_equals": return "Count is right: " + x;
      case "min_results": return "At least " + x + " " + plural(Number(x), "result", "results");
      case "ai_judge": return x || "The AI answers a question about the page";
      case "browser_count": return "Count after real clicks: " + x;
      case "ai_vision": return "AI looks at a screenshot: " + x;
      case "manual": return "You check: " + x;
      default: return x || c.rule || "Check";
    }
  }
  function isPending(c) { return c.passed === null || c.passed === undefined; }
  // Every check still waiting for a person: old "you check" checks and checks handed over at run time.
  function pendingChecks(row) {
    return (row.checks || []).filter(isPending);
  }
  // A row was handed to a person when the server says so (via "human" or a reason).
  function handedOver(r) { return !!r && (r.via === "human" || !!r.human_reason); }
  function handedReason(r) {
    if (!handedOver(r)) return "";
    if (r.human_reason) return String(r.human_reason);
    const c = pendingChecks(r).filter((x) => x.why)[0];
    return c ? String(c.why) : "";
  }
  // The question a person answers: the yes/no question when there is one, else the check in plain words.
  function questionText(c) {
    const asks = c.rule === "ai_vision" || c.rule === "ai_judge" || c.rule === "manual" || c.decided_by === "human";
    return (asks && c.expected) ? String(c.expected) : ruleText(c);
  }
  function whyText(r) {
    const why = r.why || "";
    if (r.outcome === "cant_test" && /blocked/i.test(why)) return "The site blocked us, so we can’t test this.";
    if (!why && pendingChecks(r).length) return "Waiting for your answer.";
    return why;
  }

  // ---------- counts ----------
  function counts() {
    const c = { pass: 0, fail: 0, cant: 0, manual: 0 };
    S.rows.forEach((r) => {
      if (r.outcome === "pass") c.pass++;
      else if (r.outcome === "fail") c.fail++;
      else c.cant++;
      c.manual += pendingChecks(r).length;
    });
    return c;
  }

  // ---------- grouping rows into pairs ----------
  function groupRows() {
    const map = new Map();
    S.rows.forEach((r) => {
      let g = map.get(r.pair_id);
      if (!g) {
        g = { pair_id: r.pair_id, position: r.position, user_does: r.user_does, is_priority: !!r.is_priority, rows: {}, anyFail: false, state: "done" };
        map.set(r.pair_id, g);
      }
      g.rows[r.device] = r;
      if (r.outcome === "fail") g.anyFail = true;
    });
    return map;
  }
  function placeholder(pid) {
    const m = S.meta[pid] || {};
    return { pair_id: pid, position: m.position == null ? null : m.position, user_does: m.user_does || "Pair " + pid, is_priority: !!m.is_priority, rows: {}, anyFail: false, state: S.pairState[pid] || "waiting" };
  }
  function buildItems() {
    const map = groupRows();
    const items = [];
    if (S.liveIds.length && !S.finished) {
      S.liveIds.forEach((id) => { items.push(map.get(id) || placeholder(id)); map.delete(id); });
      map.forEach((g) => items.push(g));
      return items;
    }
    const groups = Array.from(map.values());
    groups.sort((a, b) =>
      (a.is_priority ? 0 : 1) - (b.is_priority ? 0 : 1) ||
      (a.anyFail ? 0 : 1) - (b.anyFail ? 0 : 1) ||
      (a.position || 0) - (b.position || 0));
    groups.forEach((g) => items.push(g));
    // pairs we could not finish stay visible at the end, with a retry button
    S.liveIds.forEach((id) => { if (!map.has(id) && !groups.some((g) => g.pair_id === id)) items.push(placeholder(id)); });
    return items;
  }

  // ---------- header ----------
  function relTime(iso) {
    if (!iso) return "";
    const t = new Date(iso).getTime();
    if (isNaN(t)) return "";
    const s = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (s < 45) return "just now";
    const m = Math.round(s / 60);
    if (m < 60) return m + " min ago";
    const h = Math.round(m / 60);
    if (h < 24) return h + " " + plural(h, "hour", "hours") + " ago";
    return EC.fmtDate(iso);
  }
  function renderHead() {
    const run = S.run, p = S.project;
    const c = counts();
    const kind = run.kind === "changed" ? "Re-run of changed pairs" : "Full run";
    const when = relTime(run.started_at);
    const eyebrow = e(kind) + (when ? " · Started " + e(when) : "");
    const running = !S.finished && S.prog && S.prog.text && S.prog.busy !== false;
    let title, extra = "";
    if (S.finished && S.rows.length) {
      title = "Run " + e(run.run_number) + ' <span class="head-project">· ' + e(c.pass) + " of " + e(S.rows.length) + " passed</span>";
      extra = '<div class="head-pills" aria-live="polite">' +
        '<span class="pill pill-pass">' + c.pass + " pass</span>" +
        '<span class="pill pill-fail">' + c.fail + " fail</span>" +
        '<span class="pill pill-cant">' + c.cant + " can’t test</span></div>" +
        '<p class="head-note">' + e(p.name) + ". Each pair is tested twice, once as a phone and once as a laptop, so numbers count both.</p>";
    } else {
      title = "Run " + e(run.run_number) + ' <span class="head-project">· ' + e(p.name) + "</span>";
      if (S.finished) extra = '<p class="head-note">No results yet.</p>';
    }
    setHtml("head",
      '<div class="page-head"><div>' +
        '<span class="eyebrow">' + eyebrow + "</span>" +
        '<div class="head-line"><h1>' + title + "</h1>" +
        (running ? '<span class="live-status" aria-live="polite"><span class="spinner" aria-hidden="true"></span>' + e(S.prog.text) + "</span>" : "") + "</div>" +
        extra +
      "</div></div>");
    const sort = $("results-sort");
    if (sort) sort.textContent = S.finished ? "Priority first, then fails" : "In the order they run";
  }

  // ---------- "Good now?" panel ----------
  function renderChanged() {
    const el = $("changed-panel");
    if (!(S.run.kind === "changed" && S.changed && S.changed.length && S.finished)) { el.hidden = true; el.innerHTML = ""; return; }
    el.hidden = false;
    const first = !S.changedShown;
    S.changedShown = true;
    const total = S.changed.length;
    const yesN = S.changed.filter((c) => c.good_now === "yes").length;
    const noN = total - yesN;
    const items = S.changed.map((c, i) => {
      const yes = c.good_now === "yes";
      return '<li class="card changed-card' + (first ? " enter" : "") + '"' + (first ? ' style="--i:' + i + '"' : "") + ">" +
        '<div class="changed-info"><h3 class="changed-title">' + e(num(c.position)) + " " + e(c.user_does) + "</h3>" +
        '<div class="tray"><strong>You changed:</strong>' + e(c.note || "Ticked as changed") + "</div>" +
        '<div class="changed-out">' +
          '<span class="out">' + ic("smartphone") + "Phone: " + outcomePill(c.phone) + "</span>" +
          '<span class="out">' + ic("laptop") + "Laptop: " + outcomePill(c.laptop) + "</span>" +
        "</div></div>" +
        '<div class="changed-answer"><span class="good-now ' + (yes ? "is-yes" : "is-no") + (first ? " pop" : "") + '">' +
          ic(yes ? "circle-check" : "circle-x") + "Good now? " + (yes ? "Yes" : "No") + "</span></div>" +
      "</li>";
    }).join("");
    el.innerHTML =
      '<div class="changed-head"><div><span class="eyebrow">What changed</span>' +
      '<h2 id="changed-title">Run ' + e(S.run.run_number) + " · re-ran " + total + " " + plural(total, "pair", "pairs") + "</h2>" +
      "<p>Here is how each pair did after your change.</p></div>" +
      '<div class="row"><span class="pill pill-pass">' + yesN + " good now</span><span class=\"pill " + (noN ? "pill-fail" : "pill-neutral") + '">' + noN + " not yet</span></div></div>" +
      '<ul class="changed-list">' + items + "</ul>";
    icons();
  }

  // ---------- live progress (the head track draws forward as each pair finishes) ----------
  function progressMessage(html) {
    const el = $("live-progress");
    el.hidden = false;
    el.dataset.mode = "msg";
    el.innerHTML = html;
    icons();
  }
  function showProgress(text, done, total, busy) {
    const el = $("live-progress");
    S.prog = { text: text, done: done, total: total, busy: busy };
    renderHead();
    el.hidden = false;
    const pct = total ? Math.min(1, done / total) : 0;
    let fill = el.dataset.mode === "bar" ? el.querySelector(".progress-fill") : null;
    if (!fill) {
      el.dataset.mode = "bar";
      el.innerHTML =
        '<div class="run-progress">' +
          '<div class="progress" role="progressbar" aria-label="Testing progress" aria-valuemin="0">' +
            '<div class="progress-fill" style="--p:0"></div></div>' +
          '<div class="run-progress-meta"><span class="label-caps" id="pg-done"></span><span class="label-caps" id="pg-pct"></span></div>' +
        "</div>";
      fill = el.querySelector(".progress-fill");
      void fill.offsetWidth; // so the first fill animates from empty
    }
    el.querySelector(".progress").setAttribute("aria-valuemax", String(total));
    el.querySelector(".progress").setAttribute("aria-valuenow", String(done));
    fill.style.setProperty("--p", String(pct));
    const d = $("pg-done"), pc = $("pg-pct");
    if (d) d.textContent = done + " of " + total + " " + plural(total, "pair", "pairs") + " done";
    if (pc) pc.textContent = Math.round(pct * 100) + "% done";
  }
  function hideProgress() {
    const el = $("live-progress");
    S.prog = null;
    el.hidden = true;
    el.innerHTML = "";
    el.dataset.mode = "";
  }

  // ---------- manual banner ----------
  function renderBanner() {
    const n = counts().manual;
    if (!n) { setHtml("manual-banner", ""); return; }
    const site = S.project.site_url;
    setHtml("manual-banner",
      '<div class="banner banner-info" role="status"><span class="banner-icon">' + ic("eye") + "</span>" +
      '<div class="banner-body">' + n + " " + plural(n, "check needs", "checks need") + " your eyes. We couldn\u2019t finish " + plural(n, "it", "them") + " ourselves, and the reason is on the card. Open the site on your phone and laptop, then answer below." +
      (site ? ' <a href="' + e(site) + '" target="_blank" rel="noopener">Open ' + e(hostOf(site)) + "</a>" : "") + "</div></div>");
  }

  // ---------- results feed ----------
  function checkLi(c, r) {
    const pending = isPending(c);
    let res = "";
    if (r) {
      if (pending) res = '<span class="pill pill-human">Waiting for you</span>';
      else if (c.passed) res = '<span class="pill pill-pass">Pass</span>';
      else res = '<span class="pill pill-fail">Fail</span>';
    }
    const kind = EC.ui.checkKind(c, { handed: !!r && pending });
    const st = EC.ui.stepsText(c.steps);
    return '<li class="check-item">' +
      '<div class="check-line">' + EC.ui.checkTag(kind, "by") +
      '<span class="check-what">' + e(ruleText(c)) + "</span>" + res + "</div>" +
      (st ? '<p class="chk-steps">' + e(st) + "</p>" : "") +
      (r && c.why ? '<p class="check-why">' + e(c.why) + "</p>" : "") + "</li>";
  }

  function deviceChip(d) { return '<span class="chip chip-sm">' + ic(deviceIcon(d)) + deviceLabel(d) + "</span>"; }
  // "Real browser" when we clicked through the page; "You check" when we handed it to a person.
  function viaBadge(r) {
    if (!r) return "";
    if (handedOver(r)) return EC.ui.checkTag("human", "via-badge");
    if (r.via === "browser") return EC.ui.checkTag("browser", "via-badge");
    return "";
  }

  // one raised row-card; o = {pill, showed, side, checks, rid, cls, enter, i}
  function cardHtml(item, d, o) {
    return '<article class="result-card' + (o.cls ? " " + o.cls : "") + (o.enter ? " enter" : "") + '"' +
      (o.rid != null ? ' data-rid="' + e(o.rid) + '"' : "") + (o.enter ? ' style="--i:' + (o.i || 0) + '"' : "") + (o.busy ? ' aria-busy="true"' : "") + ">" +
      '<span class="rc-num" title="Pair number">' + e(num(item.position)) + "</span>" +
      '<div class="rc-body"><div class="rc-top"><h3 class="rc-title">' + e(item.user_does) + "</h3>" +
        (item.is_priority ? '<span class="pill pill-priority">Priority</span>' : "") +
        deviceChip(d) + (o.via || "") + o.pill + "</div>" + o.showed + "</div>" +
      '<div class="rc-side">' + (o.side || "") + "</div>" +
      (o.checks || "") + "</article>";
  }

  function sideHtml(r) {
    const pend = pendingChecks(r);
    if (pend.length) {
      return pend.map((c) =>
        '<div class="rc-q"><span class="label-caps">Your check</span><p>' + e(questionText(c)) + "</p>" +
        (c.id != null
          ? '<div class="manual-actions">' +
            '<button type="button" class="btn btn-secondary btn-sm" data-action="answer" data-id="' + e(c.id) + '" data-val="true">' + ic("check") + "Looks right</button>" +
            '<button type="button" class="btn btn-secondary btn-sm" data-action="answer" data-id="' + e(c.id) + '" data-val="false">' + ic("x") + "Looks wrong</button></div>"
          : "") + "</div>").join("");
    }
    const why = whyText(r);
    if (why) return '<span class="label-caps">Why</span><p class="rc-why' + (r.outcome === "fail" ? " is-fail" : r.outcome === "cant_test" ? " is-cant" : "") + '">' + e(why) + "</p>";
    const total = (r.checks || []).length;
    if (r.outcome === "pass" && total) {
      const ok = r.checks.filter((c) => c.passed === true).length;
      return '<span class="label-caps">Checks</span><p class="rc-why">' + ok + " of " + total + " " + plural(total, "check", "checks") + " passed.</p>";
    }
    return "";
  }

  function checksHtml(r) {
    if (!(r.checks && r.checks.length)) return "";
    const pend = pendingChecks(r).length;
    const isOpen = S.detailsOpen[r.result_id] !== undefined ? S.detailsOpen[r.result_id] : false;
    return '<div class="rc-checks"><details class="disclosure disclosure-inline checks" data-rid="' + e(r.result_id) + '"' + (isOpen ? " open" : "") + ">" +
      '<summary><span class="disclosure-title">Checks (' + r.checks.length + ")</span>" +
      (pend ? ' <span class="pill pill-human">' + pend + " waiting for you</span>" : "") +
      '<i data-lucide="chevron-down" class="disclosure-chev" aria-hidden="true"></i></summary>' +
      '<div class="disclosure-body"><ul class="check-list">' + r.checks.map((c) => checkLi(c, r)).join("") + "</ul></div></details></div>";
  }

  function groupHtml(item, animate, idx, pop) {
    const devs = ["phone", "laptop"];
    if (item.state !== "done") {
      return devs.map((d) => {
        const failed = item.state === "failed";
        const pill = failed ? '<span class="pill pill-cant">Couldn’t finish</span>'
          : item.state === "testing" ? '<span class="pill pill-running">Running…</span>'
          : '<span class="pill pill-neutral">Waiting…</span>';
        const showed = failed ? '<p class="rc-showed">Couldn’t finish. Try again.</p>'
          : '<div class="skeleton rc-skel" style="width:70%" aria-hidden="true"></div>';
        const side = failed
          ? '<button type="button" class="btn btn-secondary btn-sm" data-action="retry" data-pair="' + e(item.pair_id) + '">' + ic("refresh-cw") + "Try again</button>"
          : '<span class="label-caps">Why</span><div class="skeleton rc-skel" style="width:85%" aria-hidden="true"></div>';
        return cardHtml(item, d, { cls: "is-pending", pill: pill, showed: showed, side: side, busy: !failed });
      }).join("");
    }
    return devs.map((d) => {
      const r = item.rows[d] || null;
      if (!r) return cardHtml(item, d, { pill: outcomePill(null), showed: '<p class="rc-showed">No result for the ' + d + ".</p>", enter: animate, i: idx });
      const long = r.what_site_said || "";
      const open = !!S.expanded[r.result_id];
      const showed = '<div class="rc-showed-wrap">' + (long
        ? '<div class="rc-showed showed' + (open ? "" : " clamp3") + '"><span class="rc-showed-label">The site showed:</span> ' + e(long) + "</div>" +
          '<button type="button" class="disclosure-btn" data-action="more" aria-expanded="' + (open ? "true" : "false") + '"' + (open ? "" : " hidden") + ">" +
            "<span>" + (open ? "Less" : "More") + '</span><i data-lucide="chevron-down" class="disclosure-chev" aria-hidden="true"></i></button>'
        : '<div class="rc-showed"><span class="rc-showed-label">The site showed:</span> nothing came back.</div>') +
        (handedReason(r)
          ? '<div class="banner banner-info rc-handed" role="note"><span class="banner-icon">' + ic("info") + '</span><div class="banner-body"><span><strong>Why we asked you:</strong> ' + e(handedReason(r)) + "</span></div></div>"
          : "") +
        (r.status_code != null ? '<div class="status-code">Status ' + e(r.status_code) + "</div>" : "") + "</div>";
      return cardHtml(item, d, {
        rid: r.result_id, pill: outcomePill(r.outcome, pop), via: viaBadge(r), showed: showed, side: sideHtml(r), checks: checksHtml(r),
        enter: animate, i: idx,
      });
    }).join("");
  }

  function renderTable(animate) {
    const items = buildItems();
    const area = $("feed-area");
    if (!items.length) {
      area.innerHTML = '<div class="empty">' + ic("list-checks") + '<p class="empty-title">No results yet.</p><p>Results show up here as each pair is tested.</p></div>';
      icons();
      return;
    }
    area.innerHTML = '<ol class="feed" id="feed">' + items.map((it, i) =>
      '<li class="pair-group" id="pair-' + e(it.pair_id) + '" data-pair="' + e(it.pair_id) + '">' + groupHtml(it, !!animate, i, false) + "</li>").join("") + "</ol>";
    icons();
    measureClamps(area);
  }

  function renderPair(pid, animate) {
    const li = document.getElementById("pair-" + pid);
    if (!li) { renderTable(false); return; }
    const items = buildItems();
    const it = items.find((x) => String(x.pair_id) === String(pid));
    if (!it) return;
    li.innerHTML = groupHtml(it, !!animate, 0, !!animate);
    icons();
    measureClamps(li);
  }

  function measureClamps(root) {
    root.querySelectorAll(".showed.clamp3").forEach((el) => {
      const btn = el.nextElementSibling;
      if (btn && el.scrollHeight > el.clientHeight + 1) btn.hidden = false;
    });
  }

  // ---------- things to fix first ----------
  function renderPoints() {
    const sec = $("points-section");
    let body, title = "Things to fix first", side = "";
    const fails = counts().fail;
    if (!S.finished) {
      body = '<div class="card"><p class="muted">Key points appear when the run finishes.</p></div>';
    } else if (!fails) {
      body = '<div class="card"><div class="empty empty-success">' + ic("circle-check") +
        '<p class="empty-title">No fails in this run.</p><p>Nothing needs fixing first.</p></div></div>';
    } else if (!S.points.length) {
      body = '<div class="card"><p class="muted">There are fails in the results above. Key points could not be written this time.</p></div>';
    } else {
      const pts = S.points.slice().sort((a, b) => a.rank - b.rank);
      title = pts.length + " " + plural(pts.length, "thing", "things") + " to fix first";
      side = '<span class="label-caps">Most important first</span>';
      body = '<ol class="points">' + pts.map((p) => {
        const row = S.rows.find((r) => String(r.result_id) === String(p.result_id));
        const oc = row ? row.outcome : "fail";
        return '<li><article class="card point">' +
          '<div class="point-top"><span class="rank-chip ' + (oc === "cant_test" ? "is-cant" : oc === "pass" ? "is-pass" : "") + '">' + e(num(p.position)) + "</span>" +
          '<h3><span class="sr-only">Fix ' + e(p.rank) + ": </span>" + e(p.user_does) + "</h3></div>" +
          '<div class="point-sub">' + deviceChip(p.device) + "</div>" +
          (p.what_site_said ? '<div class="tray"><span class="label-caps">The site showed</span><p class="clamp4">' + e(p.what_site_said) + "</p></div>" : "") +
          '<div class="point-fix"><span class="label-caps">' + ic("wrench") + "What to change</span>" +
          '<p class="point-why">' + e(p.explanation) + "</p></div></article></li>";
      }).join("") + "</ol>";
    }
    sec.innerHTML = '<div class="section-head"><h2 class="section-title" id="points-title">' + e(title) + "</h2>" + side + "</div>" + body;
    icons();
  }

  // ---------- re-run changed ----------
  function pickItems() {
    const map = groupRows();
    const groups = Array.from(map.values());
    groups.sort((a, b) => (a.anyFail ? 0 : 1) - (b.anyFail ? 0 : 1) || (a.position || 0) - (b.position || 0));
    return groups;
  }
  function pickLabel(id, position, text, failing, isNew) {
    return '<label class="checkbox pick"><input type="checkbox" data-pick value="' + e(id) + '"' + (S.picks.has(String(id)) ? " checked" : "") + ">" +
      "<span><span class=\"num\">" + (isNew ? "New check" : e(num(position))) + "</span> " + e(text) +
      (failing ? ' <span class="pill pill-fail">Fail</span>' : "") + "</span></label>";
  }
  function draftHtml() {
    const d = S.draft;
    if (!d) return "";
    const req = (d.method || "GET") + " " + (d.request_url || "") + (d.request_body ? "  " + JSON.stringify(d.request_body) : "");
    return '<div class="draft" role="region" aria-label="Proposed check">' +
      '<span class="label-caps">Here is the check we would add</span>' +
      '<dl class="draft-list">' +
      "<div><dt>What the user does</dt><dd>" + e(d.user_does) + "</dd></div>" +
      "<div><dt>A good result has</dt><dd>" + e(d.good_result) + "</dd></div>" +
      "<div><dt>What we open</dt><dd><code>" + e(req) + "</code></dd></div>" +
      "<div><dt>Checks</dt><dd><ul class=\"check-list\">" + (d.checks || []).map((c) => checkLi(c, null)).join("") + "</ul></dd></div>" +
      "</dl>" +
      '<div class="row"><button type="button" class="btn btn-secondary" data-action="approve">' + ic("check") + "Approve and include</button>" +
      '<button type="button" class="btn btn-ghost" data-action="discard">Discard</button></div></div>';
  }
  function renderRerun() {
    const sec = $("rerun-section");
    if (!S.finished) { sec.hidden = true; return; }
    sec.hidden = false;
    const list = pickItems().map((g) => pickLabel(g.pair_id, g.position, g.user_does, g.anyFail, false));
    if (S.otherPair) list.unshift(pickLabel(S.otherPair.id, null, S.otherPair.user_does, false, true));
    sec.innerHTML = '<div class="card stack">' +
      '<div class="rr-head"><span class="icon-tile">' + ic("refresh-cw") + "</span>" +
      '<div><h2 class="section-title" id="rerun-title">Re-run what you changed</h2>' +
      "<p>Changed something on your site? Tick the pairs you changed something for and we’ll re-run just those. Nothing is ticked for you.</p></div></div>" +
      '<fieldset class="pick-fieldset"><legend class="sr-only">Pairs to re-run</legend><div class="pick-list">' + list.join("") + "</div></fieldset>" +
      '<div class="field rr-field"><label class="label" for="other-note">Anything else you changed?</label>' +
      '<textarea class="input" id="other-note" rows="3" placeholder="e.g. I moved the Add to cart button above the photos">' + e(S.note) + "</textarea>" +
      '<p class="hint">Describe it and we’ll turn it into a check.</p></div>' +
      '<div class="row"><button type="button" class="btn btn-secondary" id="tidy-btn" data-action="tidy"' + (S.note.trim() ? "" : " disabled") + ">" + ic("sparkles") + "Turn into a check</button></div>" +
      '<div id="draft-area" aria-live="polite">' + draftHtml() + "</div>" +
      '<div class="row rerun-actions"><span class="muted small" id="rerun-count" aria-live="polite"></span>' +
      '<button type="button" class="btn btn-primary" id="rerun-btn" data-action="rerun" disabled>' + ic("refresh-cw") + "Re-run changed</button></div></div>";
    icons();
    updateRerunBtn();
  }
  function updateRerunBtn() {
    const btn = $("rerun-btn");
    if (!btn) return;
    const n = S.picks.size;
    btn.disabled = n < 1;
    const c = $("rerun-count");
    if (c) {
      c.textContent = n ? n + " " + plural(n, "pair", "pairs") + " selected"
        : (S.note.trim() ? "Turn your note into a check first, or tick a pair." : "Tick at least one pair, or add another change.");
    }
  }

  // ---------- compare ----------
  function renderCompareShell() {
    const sec = $("compare-section");
    if (!S.finished) { sec.hidden = true; return; }
    sec.hidden = false;
    const head = '<div class="compare-intro"><span class="eyebrow">Before and after</span><h2 id="compare-title">Compare runs</h2></div>';
    const earlier = S.earlier.filter((r) => String(r.id) !== String(S.run.id)).sort((a, b) => b.run_number - a.run_number);
    if (!earlier.length) {
      sec.innerHTML = head + '<div class="card"><p class="muted">This is your first run. Run again later to compare.</p></div>';
      return;
    }
    const before = earlier.filter((r) => r.run_number < S.run.run_number);
    const def = (before[0] || earlier[0]).id;
    const opts = earlier.map((r) =>
      '<option value="' + e(r.id) + '"' + (r.id === def ? " selected" : "") + ">Run " + e(r.run_number) + " · " + e(EC.fmtDate(r.started_at)) + " · " + e(r.passed) + " of " + e(r.total) + " passed</option>").join("");
    sec.innerHTML = head +
      '<div class="card stack">' +
      '<div class="compare-form"><div class="field"><label class="label" for="compare-with">Compare with an earlier run</label><select class="input" id="compare-with">' + opts + "</select></div>" +
      '<button type="button" class="btn btn-secondary" id="compare-btn" data-action="compare">' + ic("git-compare") + "Compare</button></div></div>" +
      '<div id="compare-result" aria-live="polite"></div>';
    icons();
  }

  const VERDICT = {
    fixed: EC.ui.pill("fixed", "Fixed"),
    broke: EC.ui.pill("broke", "Broke"),
    same: EC.ui.pill("same", "Same"),
  };
  async function doCompare(btn, retried) {
    const sel = $("compare-with");
    if (!sel) return;
    const out = $("compare-result");
    const go = async () => {
      out.innerHTML = '<div class="skeleton skeleton-card" style="height:84px"></div>';
      try {
        const d = await EC.api("GET", "/api/runs/" + encodeURIComponent(S.run.id) + "/compare?with=" + encodeURIComponent(sel.value));
        const rows = (d.rows || []).map((r) => Object.assign({}, r, { v: String(r.verdict || "same").toLowerCase() }));
        const n = { fixed: 0, broke: 0, same: 0 };
        rows.forEach((r) => { n[r.v in n ? r.v : "same"]++; });
        rows.sort((a, b) => (a.v === "same" ? 1 : 0) - (b.v === "same" ? 1 : 0));
        const oldN = d.old_run ? d.old_run.run_number : "", newN = d.run ? d.run.run_number : S.run.run_number;
        const oldWhen = d.old_run && d.old_run.started_at ? EC.fmtDate(d.old_run.started_at) : "";
        if (!rows.length) { out.innerHTML = '<p class="muted">Nothing to compare yet.</p>'; return; }
        out.innerHTML =
          '<div class="cmp-summary"><span class="pill pill-fixed">' + n.fixed + " fixed</span><span class=\"pill pill-broke\">" + n.broke +
          ' broke</span><span class="pill pill-same">' + n.same + " same</span></div>" +
          '<div class="cmp-cols label-caps" aria-hidden="true"><span>Pair &amp; device</span>' +
          '<span class="col-run">Run ' + e(oldN) + (oldWhen ? " <small>" + e(oldWhen) + "</small>" : "") + "</span>" +
          "<span>Change</span>" +
          '<span class="col-run">Run ' + e(newN) + " <small>this run</small></span></div>" +
          '<ul class="cmp-list">' + rows.map((r, i) => {
            const broke = r.v === "broke";
            return '<li class="cmp-row enter' + (broke ? " is-broke" : "") + '" style="--i:' + i + '">' +
              '<div class="cmp-pair"><span class="icon-tile cmp-icon">' + ic(broke ? "triangle-alert" : deviceIcon(r.device)) + "</span>" +
              '<p class="cmp-title"><span class="num">' + e(num(r.position)) + "</span> " + e(r.user_does) + " " + deviceChip(r.device) + "</p></div>" +
              '<div class="cmp-a"><span class="sr-only">Run ' + e(oldN) + ": </span>" + outcomePill(r.old_outcome) + "</div>" +
              '<div class="cmp-change">' + (VERDICT[r.v] || VERDICT.same) + "</div>" +
              '<span class="cmp-arrow" aria-hidden="true">' + ic("arrow-right") + "</span>" +
              '<div class="cmp-b"><span class="sr-only">Run ' + e(newN) + ": </span>" + outcomePill(r.new_outcome) + "</div></li>";
          }).join("") + "</ul>";
        icons();
        S.compareDone = true;
      } catch (err) {
        // The automatic compare right after a run can hit a dropped connection: try once more quietly.
        if (!btn && !retried && err.status === 0) { setTimeout(() => doCompare(null, true), 1500); return; }
        out.innerHTML = '<div class="banner banner-error">' + ic("triangle-alert") + "<div>" + e(err.message) + "</div></div>";
        icons();
      }
    };
    if (btn) await EC.busy(btn, go, "Comparing…"); else await go();
  }

  // ---------- painting everything ----------
  function renderAll(animate) {
    renderHead();
    renderChanged();
    renderBanner();
    renderTable(!!animate);
    renderPoints();
    renderRerun();
    renderCompareShell();
  }

  // ---------- loading ----------
  function showFatal(html) {
    $("loading").hidden = true;
    $("screen").hidden = true;
    const f = $("fatal");
    f.hidden = false;
    f.innerHTML = html;
    icons();
  }
  function notFound() {
    showFatal('<div class="empty">' + ic("search-x") + '<p class="empty-title">We couldn’t find this run.</p>' +
      '<p>It may have been removed, or the link is not quite right.</p><a class="btn btn-secondary" href="/home.html">Go to My projects</a></div>');
  }
  function loadError(msg) {
    showFatal('<div class="banner banner-error" role="alert">' + ic("triangle-alert") + "<div>" + e(msg) + '</div><button type="button" class="btn btn-secondary btn-sm" data-action="reload">Try again</button></div>');
  }
  function applyRunData(d) {
    S.run = d.run;
    if (d.project) S.project = d.project;
    S.rows = d.rows || [];
    S.points = d.points || [];
    S.changed = d.changed || [];
    S.earlier = d.earlier_runs || S.earlier || [];
  }
  function showScreen() { $("loading").hidden = true; $("fatal").hidden = true; $("screen").hidden = false; }

  async function refetch() {
    try {
      const d = await EC.api("GET", "/api/runs/" + encodeURIComponent(RUN_ID));
      const keepEarlier = S.earlier;
      applyRunData(d);
      if (!(d.earlier_runs && d.earlier_runs.length)) S.earlier = keepEarlier;
      renderHead(); renderChanged(); renderBanner(); renderTable(false); renderPoints();
    } catch (err) { /* the saved answer is already on screen; ignore */ }
  }

  // ---------- live run ----------
  function mergeRows(rows) {
    (rows || []).forEach((r) => {
      S.rows = S.rows.filter((x) => !(x.pair_id === r.pair_id && x.device === r.device));
      S.rows.push(r);
    });
  }
  async function runPair(pid) {
    S.pairState[pid] = "testing";
    renderPair(pid, false);
    let ok = false;
    try {
      const r = await EC.api("POST", "/api/runs/" + encodeURIComponent(RUN_ID) + "/pairs/" + encodeURIComponent(pid));
      mergeRows(r.rows);
      S.pairState[pid] = "done";
      ok = true;
    } catch (err) {
      S.pairState[pid] = "failed";
    }
    renderPair(pid, ok);   // the finished pair slides in and its pills pop
    renderHead();
    renderBanner();
    return ok;
  }
  async function pairIdsToRun() {
    let ids = null;
    try {
      const raw = sessGet("ec.run." + RUN_ID + ".pairs");
      const parsed = raw ? JSON.parse(raw) : null;
      if (Array.isArray(parsed) && parsed.length) ids = parsed;
    } catch (err) { ids = null; }
    let proj = null;
    try { proj = await EC.api("GET", "/api/projects/" + encodeURIComponent(S.project.id)); } catch (err) { proj = null; }
    if (proj && proj.pairs) {
      proj.pairs.forEach((p) => { S.meta[p.id] = { position: p.position, user_does: p.user_does, is_priority: !!p.is_priority }; });
      if (!ids) {
        ids = proj.pairs.filter((p) => p.approved)
          .sort((a, b) => (b.is_priority ? 1 : 0) - (a.is_priority ? 1 : 0) || a.position - b.position)
          .map((p) => p.id);
      }
    }
    return ids || [];
  }
  async function finishRun() {
    showProgress("Finishing up and picking what to fix first…", doneCount(), S.liveIds.length);
    try {
      const r = await EC.api("POST", "/api/runs/" + encodeURIComponent(RUN_ID) + "/finish");
      if (r.run) S.run = Object.assign({}, S.run, r.run);
      S.points = r.points || [];
      S.changed = r.changed || [];
    } catch (err) {
      S.prog = null;
      renderHead();
      progressMessage('<div class="banner banner-error" role="alert">' + ic("triangle-alert") + "<div>We couldn’t wrap up the run: " + e(err.message) +
        '</div><button type="button" class="btn btn-secondary btn-sm" data-action="finish-retry">Try again</button></div>');
      return false;
    }
    S.finished = true;
    S.running = false;
    hideProgress();
    try {
      const u = new URL(location.href);
      u.searchParams.delete("start");
      history.replaceState(null, "", u.pathname + u.search + u.hash);
    } catch (err) { /* fine */ }
    renderAll(false);
    if (S.run.kind === "changed") autoCompare();
    scrollToCompareHash();
    return true;
  }
  function doneCount() { return S.liveIds.filter((id) => S.pairState[id] === "done").length; }
  async function runLive() {
    S.running = true;
    const ids = await pairIdsToRun();
    if (!ids.length) {
      S.running = false;
      S.prog = null;
      renderHead();
      progressMessage('<div class="banner banner-error" role="alert">' + ic("triangle-alert") + "<div>We couldn’t work out which pairs to test. Go back to your site and start a new run.</div></div>");
      return;
    }
    S.liveIds = ids;
    const have = groupRows();
    ids.forEach((id) => {
      const g = have.get(id);
      S.pairState[id] = g && g.rows.phone && g.rows.laptop ? "done" : "waiting";
    });
    renderAll(false);
    showProgress("running 1 of " + ids.length + "…", doneCount(), ids.length);
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      if (S.pairState[id] === "done") continue;
      showProgress("running " + (i + 1) + " of " + ids.length + "…", doneCount(), ids.length);
      await runPair(id);
      showProgress("running " + Math.min(i + 2, ids.length) + " of " + ids.length + "…", doneCount(), ids.length);
    }
    await finishRun();
  }
  // Arriving on /run.html?id=..#compare: scroll to the compare section once it exists
  function scrollToCompareHash() {
    if (location.hash !== "#compare") return;
    const sec = $("compare-section");
    if (sec && !sec.hidden) sec.scrollIntoView({ behavior: EC.ui.reducedMotion() ? "auto" : "smooth", block: "start" });
  }
  function autoCompare() {
    if ($("compare-with")) doCompare(null);
  }

  // ---------- actions ----------
  async function answerCheck(btn) {
    const id = btn.dataset.id, val = btn.dataset.val === "true";
    const wrap = btn.closest(".manual-actions");
    const btns = wrap ? Array.from(wrap.querySelectorAll("button")) : [btn];
    btns.forEach((b) => { b.disabled = true; });
    btn.setAttribute("aria-busy", "true");
    try {
      const r = await EC.api("PATCH", "/api/result-checks/" + encodeURIComponent(id), { passed: val });
      const chk = r && r.check;
      let touched = null;
      S.rows.forEach((row) => {
        (row.checks || []).forEach((c, i) => {
          if (String(c.id) === String(id)) {
            row.checks[i] = chk ? Object.assign({}, c, chk) : Object.assign({}, c, { passed: val });
            touched = row;
          }
        });
      });
      EC.toast("Thanks — saved.", "success");
      if (touched) { renderPair(touched.pair_id, false); renderBanner(); renderHead(); }
      if (!S.running) refetch();
    } catch (err) {
      if (err.status === 409) { EC.toast("That one was already answered.", "info"); refetch(); }
      else { EC.toast(err.message, "error"); btns.forEach((b) => { b.disabled = false; }); }
      btn.removeAttribute("aria-busy");
    }
  }

  async function retryPair(pid) {
    const ok = await runPair(pid);
    if (ok && S.finished) {
      try {
        const r = await EC.api("POST", "/api/runs/" + encodeURIComponent(RUN_ID) + "/finish");
        if (r.run) S.run = Object.assign({}, S.run, r.run);
        S.points = r.points || S.points;
        S.changed = r.changed || S.changed;
      } catch (err) { /* table is still right; points refresh on reload */ }
      renderAll(false);
    }
  }

  async function tidy(btn) {
    const ta = $("other-note");
    const note = ta.value.trim();
    if (!note) return;
    await EC.busy(btn, async () => {
      try {
        const r = await EC.api("POST", "/api/pairs/tidy", {
          rough_text: note,
          site_url: S.project.site_url,
          kind: "change",
        });
        S.draft = r.pair;
        $("draft-area").innerHTML = draftHtml();
        icons();
      } catch (err) {
        EC.toast(err.message || "We couldn’t turn that into a check. Try describing it again.", "error");
      }
    }, "Working on it…");
  }
  async function approveDraft(btn) {
    const d = S.draft;
    if (!d) return;
    await EC.busy(btn, async () => {
      try {
        const body = Object.assign({}, d, { source: "builder", approved: true });
        const r = await EC.api("POST", "/api/projects/" + encodeURIComponent(S.project.id) + "/pairs", body);
        S.otherPair = { id: r.id, user_does: d.user_does };
        S.picks.add(String(r.id));
        S.draft = null;
        renderRerun();
        EC.toast("Added to your re-run.", "success");
      } catch (err) {
        EC.toast(err.message, "error");
      }
    }, "Adding…");
  }
  async function rerun(btn) {
    const ids = [];
    const boxes = document.querySelectorAll("[data-pick]");
    boxes.forEach((b) => { if (b.checked) ids.push(isNaN(Number(b.value)) ? b.value : Number(b.value)); });
    if (!ids.length) return;
    const note = ($("other-note") || {}).value || "";
    const other = S.otherPair && S.picks.has(String(S.otherPair.id)) ? S.otherPair.id : null;
    await EC.busy(btn, async () => {
      try {
        const r = await EC.api("POST", "/api/projects/" + encodeURIComponent(S.project.id) + "/runs", {
          kind: "changed", pair_ids: ids, other_changes: note.trim(), other_pair_id: other,
        });
        sessSet("ec.run." + r.run.id + ".pairs", JSON.stringify(r.pair_ids || ids));
        location.href = "/run.html?id=" + encodeURIComponent(r.run.id) + "&start=1";
        await new Promise(() => {}); // stay greyed out while the page changes
      } catch (err) {
        EC.toast(err.message, "error");
      }
    }, "Starting…");
  }

  function onClick(ev) {
    const t = ev.target.closest("[data-action]");
    if (!t) return;
    const a = t.dataset.action;
    if (a === "more") {
      const box = t.previousElementSibling;
      const rid = t.closest(".result-card").dataset.rid;
      const open = box.classList.toggle("clamp3") === false;
      S.expanded[rid] = open;
      t.setAttribute("aria-expanded", open ? "true" : "false");
      const lbl = t.querySelector("span");
      if (lbl) lbl.textContent = open ? "Less" : "More";
    } else if (a === "answer") answerCheck(t);
    else if (a === "retry") retryPair(t.dataset.pair);
    else if (a === "tidy") tidy(t);
    else if (a === "approve") approveDraft(t);
    else if (a === "discard") { S.draft = null; $("draft-area").innerHTML = ""; }
    else if (a === "rerun") rerun(t);
    else if (a === "compare") doCompare(t);
    else if (a === "finish-retry") finishRun();
    else if (a === "reload") location.reload();
  }

  // ---------- boot ----------
  async function boot() {
    if (!EC.requireLogin()) return;
    bar = EC.ui.topbar({ page: "run", runId: RUN_ID });
    icons();
    document.addEventListener("click", onClick);
    document.addEventListener("change", (ev) => {
      const b = ev.target.closest && ev.target.closest("[data-pick]");
      if (!b) return;
      if (b.checked) S.picks.add(String(b.value)); else S.picks.delete(String(b.value));
      updateRerunBtn();
    });
    document.addEventListener("input", (ev) => {
      if (ev.target.id !== "other-note") return;
      S.note = ev.target.value;
      const tb = $("tidy-btn");
      if (tb && !tb.hasAttribute("aria-busy")) tb.disabled = !S.note.trim();
    });
    // remember which checks the builder opened or closed
    document.addEventListener("toggle", (ev) => {
      const d = ev.target;
      if (d.classList && d.classList.contains("checks")) S.detailsOpen[d.dataset.rid] = d.open;
      if (d.id === "how-to-read") {
        if (d.dataset.auto) { delete d.dataset.auto; return; } // phone default, not the reader's choice
        storeSet(KEY_CLOSED, d.open ? "0" : "1");
      }
    }, true);
    const howEl = $("how-to-read");
    if (storeGet(KEY_CLOSED) === "1") howEl.removeAttribute("open");
    else if (window.matchMedia("(max-width: 640px)").matches && howEl.open) { howEl.dataset.auto = "1"; howEl.open = false; }

    if (!RUN_ID) { notFound(); return; }
    let d;
    try {
      d = await EC.api("GET", "/api/runs/" + encodeURIComponent(RUN_ID));
    } catch (err) {
      if (err.status === 404) notFound(); else loadError(err.message);
      return;
    }
    applyRunData(d);
    document.title = "Run " + S.run.run_number + " · Eval Co-pilot";
    EC.ui.remember({ projectId: S.project && S.project.id, projectName: S.project && S.project.name, runId: RUN_ID });
    bar.update({ projectId: S.project && S.project.id, projectName: S.project && S.project.name, runNumber: S.run.run_number });
    showScreen();
    if (LIVE) {
      renderHead();
      renderPoints();
      runLive().catch(() => { S.running = false; S.prog = null; renderHead(); progressMessage('<div class="banner banner-error" role="alert">' + ic("triangle-alert") + "<div>Something went wrong while testing. Reload the page to see what finished.</div></div>"); });
    } else {
      S.finished = true;
      renderAll(true);
      if (S.run.kind === "changed") autoCompare();
      scrollToCompareHash();
    }
  }
  boot();
})();
