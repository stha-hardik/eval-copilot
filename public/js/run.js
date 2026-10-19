// Results screen: /run.html?id=<run id>[&start=1]
// Live mode (start=1) tests one pair at a time and fills the table as answers arrive.
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
  };

  const $ = (id) => document.getElementById(id);

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

  function outcomePill(o) {
    if (o === "pass") return '<span class="pill pill-pass">' + ic("check") + "Pass</span>";
    if (o === "fail") return '<span class="pill pill-fail">' + ic("x") + "Fail</span>";
    if (o === "cant_test") return '<span class="pill pill-cant">' + ic("ban") + "Can’t test</span>";
    return '<span class="pill pill-neutral">' + ic("minus") + "Not tested</span>";
  }
  function deviceLabel(d) { return d === "phone" ? "Phone" : "Laptop"; }
  function deviceIcon(d) { return d === "phone" ? "smartphone" : "laptop"; }
  function deviceHtml(d) {
    return '<span class="device">' + ic(deviceIcon(d)) + deviceLabel(d) + "</span>";
  }

  // ---------- plain-words check text ----------
  function ruleText(c) {
    const x = c.expected == null ? "" : String(c.expected);
    switch (c.rule) {
      case "status_ok": return "Page opens";
      case "text_has": return "Shows “" + x + "”";
      case "text_absent": return "Doesn’t show “" + x + "”";
      case "count_equals": return "Count is right: " + x;
      case "min_results": return "At least " + x + " " + plural(Number(x), "result", "results");
      case "ai_judge": return x || "The AI judges the page";
      case "manual": return "You look: " + x;
      default: return x || c.rule || "Check";
    }
  }
  function decidedBy(c) {
    if (c.decided_by === "ai") return "AI";
    if (c.decided_by === "human" || c.rule === "manual") return "You";
    return "Code";
  }
  function isPending(c) { return c.passed === null || c.passed === undefined; }
  function pendingManual(row) {
    return (row.checks || []).filter((c) => isPending(c) && (c.rule === "manual" || c.decided_by === "human"));
  }
  function whyText(r) {
    const why = r.why || "";
    if (r.outcome === "cant_test" && /blocked/i.test(why)) return "The site blocked us, so we can’t test this.";
    if (!why && pendingManual(r).length) return "Waiting for you to look at the site.";
    return why;
  }

  // ---------- counts ----------
  function counts() {
    const c = { pass: 0, fail: 0, cant: 0, manual: 0 };
    S.rows.forEach((r) => {
      if (r.outcome === "pass") c.pass++;
      else if (r.outcome === "fail") c.fail++;
      else c.cant++;
      c.manual += pendingManual(r).length;
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
  function renderHead() {
    const run = S.run, p = S.project;
    const c = counts();
    const kind = run.kind === "changed" ? "Re-run of changed pairs" : "Full run";
    const summary = S.rows.length
      ? '<strong>' + c.pass + "</strong> passed · <strong>" + c.fail + "</strong> failed · <strong>" + c.cant + "</strong> can’t test"
      : "No results yet";
    setHtml("head",
      '<div class="page-head">' +
        "<div>" +
          '<a class="back-link" href="/project.html?id=' + encodeURIComponent(p.id) + '">' + ic("arrow-left") + "Back to " + e(p.name) + "</a>" +
          "<h1>Run " + e(run.run_number) + "</h1>" +
          '<p class="run-kind">' + e(kind) + " · " + e(EC.fmtDate(run.started_at)) + "</p>" +
          '<p class="run-summary" aria-live="polite">' + summary + "</p>" +
          (S.rows.length ? '<p class="small muted">Each pair is tested twice, once as a phone and once as a laptop, so numbers count both.</p>' : "") +
        "</div>" +
      "</div>");
  }

  // ---------- "Did it work?" ----------
  function renderChanged() {
    const el = $("changed-panel");
    if (!(S.run.kind === "changed" && S.changed && S.changed.length && S.finished)) { el.hidden = true; el.innerHTML = ""; return; }
    el.hidden = false;
    const items = S.changed.map((c) => {
      const yes = c.good_now === "yes";
      return '<li class="changed-item">' +
        '<div class="changed-info"><p class="changed-title">' + e(num(c.position)) + " " + e(c.user_does) + "</p>" +
        '<p class="small muted">What you changed: ' + e(c.note || "Ticked as changed") + "</p></div>" +
        '<div class="changed-out">' +
          '<span class="out"><span class="small muted">Phone</span>' + outcomePill(c.phone) + "</span>" +
          '<span class="out"><span class="small muted">Laptop</span>' + outcomePill(c.laptop) + "</span>" +
        "</div>" +
        '<div class="changed-answer"><span class="pill answer ' + (yes ? "pill-pass" : "pill-fail") + '">' +
          ic(yes ? "check" : "x") + "Good now? " + (yes ? "Yes" : "No") + "</span></div>" +
      "</li>";
    }).join("");
    el.innerHTML = '<div class="card stack"><h2 class="section-title" id="changed-title">Did it work?</h2><ul class="changed-list">' + items + "</ul></div>";
    icons();
  }

  // ---------- live progress ----------
  function showProgress(text, done, total, busy) {
    const el = $("live-progress");
    el.hidden = false;
    const pct = total ? Math.min(1, done / total) : 0;
    el.innerHTML =
      '<div class="progress-wrap" aria-live="polite">' +
        '<p class="progress-text">' + (busy === false ? "" : '<span class="spinner" aria-hidden="true"></span>') + e(text) + "</p>" +
        '<div class="progress" role="progressbar" aria-label="Testing progress" aria-valuemin="0" aria-valuemax="' + total + '" aria-valuenow="' + done + '">' +
          '<span style="transform:scaleX(' + pct + ')"></span></div>' +
      "</div>";
  }
  function hideProgress() { const el = $("live-progress"); el.hidden = true; el.innerHTML = ""; }

  // ---------- manual banner ----------
  function renderBanner() {
    const n = counts().manual;
    if (!n) { setHtml("manual-banner", ""); return; }
    const site = S.project.site_url;
    setHtml("manual-banner",
      '<div class="banner banner-info" role="status">' + ic("eye") +
      "<div>" + n + " " + plural(n, "check needs", "checks need") + " your eyes. Open the site on your phone and laptop, then answer " + plural(n, "it", "them") + " below." +
      (site ? ' <a href="' + e(site) + '" target="_blank" rel="noopener">Open ' + e(hostOf(site)) + "</a>" : "") + "</div></div>");
  }

  // ---------- results table ----------
  function checkLi(c, r) {
    const pending = isPending(c);
    let res = "";
    if (r) {
      if (pending) res = '<span class="pill pill-human">' + ic("eye") + "Needs a look</span>";
      else if (c.passed) res = '<span class="pill pill-pass">' + ic("check") + "Pass</span>";
      else res = '<span class="pill pill-fail">' + ic("x") + "Fail</span>";
    }
    let extra = "";
    if (r && pending && c.id != null) {
      extra = '<div class="manual-actions">' +
        '<button type="button" class="btn btn-secondary btn-sm" data-action="answer" data-id="' + e(c.id) + '" data-val="true">' + ic("check") + "Looks right</button>" +
        '<button type="button" class="btn btn-secondary btn-sm" data-action="answer" data-id="' + e(c.id) + '" data-val="false">' + ic("x") + "Looks wrong</button></div>";
    }
    return '<li class="check-item">' +
      '<div class="check-line"><span class="pill pill-neutral by" title="Who decided">' + e(decidedBy(c)) + "</span>" +
      '<span class="check-what">' + e(ruleText(c)) + "</span>" + res + "</div>" +
      (r && c.why ? '<p class="check-why small muted">' + e(c.why) + "</p>" : "") + extra + "</li>";
  }

  function leadCells(item, span) {
    return '<td class="c-num" data-label="#" rowspan="' + span + '"><span class="num">' + e(num(item.position)) + "</span>" +
      (item.is_priority ? ' <span class="pill pill-priority">' + ic("flag") + "Priority</span>" : "") + "</td>" +
      '<td class="c-does" data-label="What the user does" rowspan="' + span + '">' + e(item.user_does) + "</td>";
  }
  function dupCell(item) {
    return '<td class="dup"><span class="num">' + e(num(item.position)) + "</span> " + e(item.user_does) +
      (item.is_priority ? ' <span class="pill pill-priority">' + ic("flag") + "Priority</span>" : "") + "</td>";
  }

  function pairHtml(item) {
    const devs = ["phone", "laptop"];
    let html = "";
    if (item.state !== "done") {
      devs.forEach((d, i) => {
        let result, showed = '<span class="muted">—</span>', why = '<span class="muted">—</span>';
        if (item.state === "testing") result = '<span class="status-wait"><span class="spinner" aria-hidden="true"></span>Testing…</span>';
        else if (item.state === "failed") {
          result = '<span class="pill pill-cant">' + ic("ban") + "Couldn’t finish</span>";
          why = '<span>Couldn’t finish — try again.</span> <button type="button" class="btn btn-secondary btn-sm" data-action="retry" data-pair="' + e(item.pair_id) + '">' + ic("refresh-cw") + "Try again</button>";
        } else result = '<span class="status-wait muted">' + ic("clock") + "Waiting…</span>";
        html += '<tr class="res-row is-pending">' + (i === 0 ? leadCells(item, 2) : dupCell(item)) +
          '<td data-label="Device">' + deviceHtml(d) + "</td>" +
          '<td data-label="Result">' + result + "</td>" +
          '<td data-label="What the site showed"' + (item.state === "failed" ? "" : ' class="is-empty"') + ">" + showed + "</td>" +
          '<td data-label="Why"' + (item.state === "failed" ? "" : ' class="is-empty"') + ">" + why + "</td></tr>";
      });
      return html;
    }
    const rs = devs.map((d) => item.rows[d] || null);
    const span = rs.reduce((n, r) => n + 1 + (r && r.checks && r.checks.length ? 1 : 0), 0);
    rs.forEach((r, i) => {
      const d = devs[i];
      const lead = i === 0 ? leadCells(item, span) : dupCell(item);
      if (!r) {
        html += '<tr class="res-row">' + lead + '<td data-label="Device">' + deviceHtml(d) + '</td><td colspan="3" class="muted">No result for the ' + d + ".</td></tr>";
        return;
      }
      const long = r.what_site_said || "";
      const open = !!S.expanded[r.result_id];
      const showed = long
        ? '<div class="showed' + (open ? "" : " clamp3") + '">' + e(long) + "</div>" +
          '<button type="button" class="link-btn" data-action="more"' + (open ? "" : " hidden") + ">" + (open ? "Less" : "More") + "</button>"
        : '<span class="muted">Nothing came back.</span>';
      const status = r.status_code != null ? '<div class="status-code small muted">Status ' + e(r.status_code) + "</div>" : "";
      const why = whyText(r);
      html += '<tr class="res-row' + (r.checks && r.checks.length ? " has-checks" : "") + '" data-rid="' + e(r.result_id) + '">' + lead +
        '<td data-label="Device">' + deviceHtml(d) + "</td>" +
        '<td data-label="Result">' + outcomePill(r.outcome) + "</td>" +
        '<td data-label="What the site showed">' + showed + status + "</td>" +
        '<td data-label="Why">' + (why ? e(why) : '<span class="muted">—</span>') + "</td></tr>";
      if (r.checks && r.checks.length) {
        const pend = pendingManual(r).length;
        const isOpen = S.detailsOpen[r.result_id] !== undefined ? S.detailsOpen[r.result_id] : pend > 0;
        html += '<tr class="checks-tr"><td class="checks-cell" colspan="4">' +
          '<details class="checks" data-rid="' + e(r.result_id) + '"' + (isOpen ? " open" : "") + ">" +
          "<summary>" + ic("chevron-right") + "Checks (" + r.checks.length + ")" +
          (pend ? ' <span class="pill pill-human">' + pend + " to look at</span>" : "") + "</summary>" +
          '<ul class="check-list">' + r.checks.map((c) => checkLi(c, r)).join("") + "</ul></details></td></tr>";
      }
    });
    return html;
  }

  function tableShell() {
    return '<div class="table-wrap results-wrap"><table class="table stack-mobile results" id="results-table">' +
      "<thead><tr>" +
      '<th class="col-num">#</th><th class="col-does">What the user does</th><th class="col-dev">Device</th>' +
      '<th class="col-res">Result</th><th class="col-showed">What the site showed</th><th class="col-why">Why</th>' +
      "</tr></thead></table></div>";
  }

  function renderTable() {
    const items = buildItems();
    const area = $("table-area");
    if (!items.length) {
      area.innerHTML = '<div class="empty">' + ic("list-checks") + '<p class="empty-title">No results yet.</p><p>Results show up here as each pair is tested.</p></div>';
      icons();
      return;
    }
    area.innerHTML = tableShell();
    const table = $("results-table");
    items.forEach((it) => {
      const tb = document.createElement("tbody");
      tb.id = "pair-" + it.pair_id;
      tb.dataset.pair = it.pair_id;
      tb.innerHTML = pairHtml(it);
      table.appendChild(tb);
    });
    icons();
    measureClamps(table);
  }

  function renderPair(pid) {
    const tb = document.getElementById("pair-" + pid);
    if (!tb) { renderTable(); return; }
    const items = buildItems();
    const it = items.find((x) => String(x.pair_id) === String(pid));
    if (!it) return;
    tb.innerHTML = pairHtml(it);
    icons();
    measureClamps(tb);
  }

  function measureClamps(root) {
    root.querySelectorAll(".showed.clamp3").forEach((el) => {
      const btn = el.nextElementSibling;
      if (btn && el.scrollHeight > el.clientHeight + 1) btn.hidden = false;
    });
  }

  // ---------- key points ----------
  function renderPoints() {
    const sec = $("points-section");
    let body;
    const fails = counts().fail;
    if (!S.finished) {
      body = '<div class="card"><p class="muted">Key points appear when the run finishes.</p></div>';
    } else if (!fails) {
      body = '<div class="card"><div class="empty empty-success">' + ic("circle-check") +
        '<p class="empty-title">No fails in this run.</p><p>Nothing needs fixing first.</p></div></div>';
    } else if (!S.points.length) {
      body = '<div class="card"><p class="muted">There are fails in the table above. Key points could not be written this time.</p></div>';
    } else {
      body = '<ol class="points">' + S.points.slice().sort((a, b) => a.rank - b.rank).map((p) =>
        '<li class="card point"><span class="rank" aria-hidden="true">' + e(p.rank) + "</span><div class=\"point-body\">" +
        '<h3><span class="sr-only">Fix ' + e(p.rank) + ": </span>" + e(num(p.position)) + " " + e(p.user_does) + " · " + e(deviceLabel(p.device)) + "</h3>" +
        '<p class="point-why">' + e(p.explanation) + "</p>" +
        (p.what_site_said ? '<p class="small muted clamp3">What the site showed: ' + e(p.what_site_said) + "</p>" : "") +
        "</div></li>").join("") + "</ol>";
    }
    sec.innerHTML = '<h2 class="section-title" id="points-title">What to fix first</h2>' + body;
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
      (failing ? ' <span class="pill pill-fail">' + ic("x") + "Fail</span>" : "") + "</span></label>";
  }
  function draftHtml() {
    const d = S.draft;
    if (!d) return "";
    const req = (d.method || "GET") + " " + (d.request_url || "") + (d.request_body ? "  " + JSON.stringify(d.request_body) : "");
    return '<div class="draft" role="region" aria-label="Proposed check">' +
      '<p class="label">Here is the check we would add</p>' +
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
    const failIds = new Set();
    const list = pickItems().map((g) => { if (g.anyFail) failIds.add(g.pair_id); return pickLabel(g.pair_id, g.position, g.user_does, g.anyFail, false); });
    if (S.otherPair) list.unshift(pickLabel(S.otherPair.id, null, S.otherPair.user_does, false, true));
    sec.innerHTML = '<div class="card stack">' +
      '<div><h2 class="section-title" id="rerun-title">Changed something on your site? Re-run just those pairs.</h2>' +
      '<p class="muted small rerun-help">Tick the pairs you changed something for. Nothing is ticked for you.</p></div>' +
      '<fieldset class="pick-fieldset"><legend class="sr-only">Pairs to re-run</legend><div class="pick-list">' + list.join("") + "</div></fieldset>" +
      '<div class="field"><label class="label" for="other-note">Other changes</label>' +
      '<textarea class="input" id="other-note" rows="3" placeholder="e.g. I moved the Add to cart button above the photos">' + e(S.note) + "</textarea>" +
      '<p class="hint">Anything else you changed? Describe it and we’ll turn it into a check.</p></div>' +
      '<div class="row"><button type="button" class="btn btn-secondary" id="tidy-btn" data-action="tidy"' + (S.note.trim() ? "" : " disabled") + ">" + ic("sparkles") + "Turn into a check</button></div>" +
      '<div id="draft-area" aria-live="polite">' + draftHtml() + "</div>" +
      '<div class="row rerun-actions"><button type="button" class="btn btn-primary" id="rerun-btn" data-action="rerun" disabled>' + ic("refresh-cw") + "Re-run changed</button>" +
      '<span class="muted small" id="rerun-count"></span></div></div>';
    icons();
    updateRerunBtn();
  }
  function updateRerunBtn() {
    const btn = $("rerun-btn");
    if (!btn) return;
    const n = S.picks.size;
    btn.disabled = n < 1;
    const c = $("rerun-count");
    if (c) c.textContent = n ? n + " " + plural(n, "pair", "pairs") + " selected" : "Tick at least one pair, or add another change.";
  }

  // ---------- compare ----------
  function renderCompareShell() {
    const sec = $("compare-section");
    if (!S.finished) { sec.hidden = true; return; }
    sec.hidden = false;
    const earlier = S.earlier.filter((r) => String(r.id) !== String(S.run.id)).sort((a, b) => b.run_number - a.run_number);
    if (!earlier.length) {
      sec.innerHTML = '<h2 class="section-title" id="compare-title">Compare with an earlier run</h2>' +
        '<div class="card"><p class="muted">This is your first run. Run again later to compare.</p></div>';
      return;
    }
    const before = earlier.filter((r) => r.run_number < S.run.run_number);
    const def = (before[0] || earlier[0]).id;
    const opts = earlier.map((r) =>
      '<option value="' + e(r.id) + '"' + (r.id === def ? " selected" : "") + ">Run " + e(r.run_number) + " · " + e(EC.fmtDate(r.started_at)) + " · " + e(r.passed) + " of " + e(r.total) + " passed</option>").join("");
    sec.innerHTML = '<h2 class="section-title" id="compare-title">Compare with an earlier run</h2>' +
      '<div class="card stack">' +
      '<div class="compare-form"><div class="field"><label class="label" for="compare-with">Earlier run</label><select class="input" id="compare-with">' + opts + "</select></div>" +
      '<button type="button" class="btn btn-secondary" id="compare-btn" data-action="compare">' + ic("git-compare") + "Compare</button></div>" +
      '<div id="compare-result" aria-live="polite"></div></div>';
    icons();
  }

  const VERDICT = {
    fixed: ['<span class="pill pill-fixed">' + ic("check") + "Fixed</span>", 0],
    broke: ['<span class="pill pill-broke">' + ic("x") + "Broke</span>", 0],
    same: ['<span class="pill pill-same">' + ic("minus") + "Same</span>", 1],
  };
  async function doCompare(btn) {
    const sel = $("compare-with");
    if (!sel) return;
    const out = $("compare-result");
    const go = async () => {
      out.innerHTML = '<div class="skeleton" style="height:56px"></div>';
      try {
        const d = await EC.api("GET", "/api/runs/" + encodeURIComponent(S.run.id) + "/compare?with=" + encodeURIComponent(sel.value));
        const rows = (d.rows || []).map((r) => Object.assign({}, r, { v: String(r.verdict || "same").toLowerCase() }));
        const n = { fixed: 0, broke: 0, same: 0 };
        rows.forEach((r) => { n[r.v in n ? r.v : "same"]++; });
        rows.sort((a, b) => (a.v === "same" ? 1 : 0) - (b.v === "same" ? 1 : 0));
        const oldN = d.old_run ? d.old_run.run_number : "", newN = d.run ? d.run.run_number : S.run.run_number;
        if (!rows.length) { out.innerHTML = '<p class="muted">Nothing to compare yet.</p>'; return; }
        out.innerHTML = '<p class="compare-summary"><strong>' + n.fixed + "</strong> fixed · <strong>" + n.broke + "</strong> broke · <strong>" + n.same + "</strong> same</p>" +
          '<div class="table-wrap"><table class="table stack-mobile compare-table"><thead><tr><th>#</th><th>What the user does</th><th>Device</th><th>Run ' + e(oldN) + "</th><th>Run " + e(newN) + "</th><th>Change</th></tr></thead><tbody>" +
          rows.map((r) => "<tr>" +
            '<td data-label="#" class="c-num"><span class="num">' + e(num(r.position)) + "</span></td>" +
            '<td data-label="What the user does" class="c-does">' + e(r.user_does) + "</td>" +
            '<td data-label="Device">' + deviceHtml(r.device) + "</td>" +
            '<td data-label="Run ' + e(oldN) + '">' + outcomePill(r.old_outcome) + "</td>" +
            '<td data-label="Run ' + e(newN) + '">' + outcomePill(r.new_outcome) + "</td>" +
            '<td data-label="Change">' + (VERDICT[r.v] || VERDICT.same)[0] + "</td></tr>").join("") +
          "</tbody></table></div>";
        icons();
        S.compareDone = true;
      } catch (err) {
        out.innerHTML = '<div class="banner banner-error">' + ic("triangle-alert") + "<div>" + e(err.message) + "</div></div>";
        icons();
      }
    };
    if (btn) await EC.busy(btn, go, "Comparing…"); else await go();
  }

  // ---------- painting everything ----------
  function renderAll() {
    renderHead();
    renderChanged();
    renderBanner();
    renderTable();
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
      '<p>It may have been removed, or the link is not quite right.</p><a class="btn btn-secondary" href="/home.html">Go to my sites</a></div>');
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
      renderHead(); renderChanged(); renderBanner(); renderTable(); renderPoints();
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
    renderPair(pid);
    let ok = false;
    try {
      const r = await EC.api("POST", "/api/runs/" + encodeURIComponent(RUN_ID) + "/pairs/" + encodeURIComponent(pid));
      mergeRows(r.rows);
      S.pairState[pid] = "done";
      ok = true;
    } catch (err) {
      S.pairState[pid] = "failed";
    }
    renderPair(pid);
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
    showProgress("Finishing up and picking what to fix first…", S.liveIds.length, S.liveIds.length);
    try {
      const r = await EC.api("POST", "/api/runs/" + encodeURIComponent(RUN_ID) + "/finish");
      if (r.run) S.run = Object.assign({}, S.run, r.run);
      S.points = r.points || [];
      S.changed = r.changed || [];
    } catch (err) {
      $("live-progress").innerHTML = '<div class="banner banner-error" role="alert">' + ic("triangle-alert") + "<div>We couldn’t wrap up the run: " + e(err.message) +
        '</div><button type="button" class="btn btn-secondary btn-sm" data-action="finish-retry">Try again</button></div>';
      icons();
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
    renderAll();
    if (S.run.kind === "changed") autoCompare();
    return true;
  }
  async function runLive() {
    S.running = true;
    const ids = await pairIdsToRun();
    if (!ids.length) {
      S.running = false;
      showProgress("", 0, 0, false);
      $("live-progress").innerHTML = '<div class="banner banner-error" role="alert">' + ic("triangle-alert") + "<div>We couldn’t work out which pairs to test. Go back to your site and start a new run.</div></div>";
      icons();
      return;
    }
    S.liveIds = ids;
    const have = groupRows();
    ids.forEach((id) => {
      const g = have.get(id);
      S.pairState[id] = g && g.rows.phone && g.rows.laptop ? "done" : "waiting";
    });
    renderAll();
    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      showProgress("Testing pair " + (i + 1) + " of " + ids.length + "…", i, ids.length);
      if (S.pairState[id] === "done") continue;
      await runPair(id);
    }
    await finishRun();
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
      if (touched) { renderPair(touched.pair_id); renderBanner(); renderHead(); }
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
      renderAll();
    }
  }

  async function tidy(btn) {
    const ta = $("other-note");
    const note = ta.value.trim();
    if (!note) return;
    await EC.busy(btn, async () => {
      try {
        const r = await EC.api("POST", "/api/pairs/tidy", {
          rough_text: "The builder changed this on their site: " + note + "\nCheck that the change works.",
          site_url: S.project.site_url,
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
      const rid = t.closest("tr").dataset.rid;
      const open = box.classList.toggle("clamp3") === false;
      S.expanded[rid] = open;
      t.textContent = open ? "Less" : "More";
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
    const s = EC.getSession();
    $("user-email").textContent = (s && s.user && s.user.email) || "";
    $("logout").addEventListener("click", EC.logout);
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
      if (d.id === "how-to-read") storeSet(KEY_CLOSED, d.open ? "0" : "1");
    }, true);
    if (storeGet(KEY_CLOSED) === "1") $("how-to-read").removeAttribute("open");

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
    showScreen();
    if (LIVE) {
      renderHead();
      renderPoints();
      runLive().catch(() => { S.running = false; showProgress("", 0, 0, false); $("live-progress").innerHTML = '<div class="banner banner-error" role="alert">' + ic("triangle-alert") + "<div>Something went wrong while testing. Reload the page to see what finished.</div></div>"; icons(); });
    } else {
      S.finished = true;
      renderAll();
      if (S.run.kind === "changed") autoCompare();
    }
  }
  boot();
})();
