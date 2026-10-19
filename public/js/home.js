// Screen 2: Home, "My projects".
(function () {
  if (!EC.requireLogin()) return;

  var content = document.getElementById("content");
  var newBtn = document.getElementById("new-site");
  var session = EC.getSession();

  document.getElementById("user-email").textContent = (session && session.user && session.user.email) || "";
  document.getElementById("logout").addEventListener("click", function () { EC.logout(); });
  newBtn.addEventListener("click", function () { openForm(newBtn); });

  function icons() { if (window.lucide) window.lucide.createIcons(); }

  // ---------- States ----------
  function showLoading() {
    var cards = "";
    for (var i = 0; i < 3; i++) cards += '<li><div class="skeleton skeleton-card"></div></li>';
    content.innerHTML = '<ul class="project-grid" aria-busy="true" aria-label="Loading your projects">' + cards + "</ul>";
  }

  function showError(msg) {
    content.innerHTML =
      '<div class="banner banner-error enter" role="alert"><span class="banner-icon"><i data-lucide="circle-alert" aria-hidden="true"></i></span>' +
      '<div class="banner-body"><span>' + EC.esc(msg) + '</span></div><button class="btn btn-secondary btn-sm" id="retry" type="button">Try again</button></div>';
    icons();
    document.getElementById("retry").addEventListener("click", load);
  }

  function showEmpty() {
    content.innerHTML =
      '<div class="card empty enter">' +
      '<span class="empty-icon"><i data-lucide="folder-plus" aria-hidden="true"></i></span>' +
      '<h2 class="empty-title">No projects yet. Add the first website you want to test.</h2>' +
      '<button class="btn btn-secondary" id="first-site" type="button"><i data-lucide="plus" aria-hidden="true"></i>Add a website</button></div>';
    icons();
    var b = document.getElementById("first-site");
    b.addEventListener("click", function () { openForm(b); });
  }

  // "12 Oct", with the year only when it is not this year
  function shortDate(iso) {
    if (!iso) return "";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    var opts = { day: "numeric", month: "short" };
    if (d.getFullYear() !== new Date().getFullYear()) opts.year = "numeric";
    return d.toLocaleDateString(undefined, opts);
  }

  function statusPill(p) {
    var r = p.last_run;
    if (!r) return '<span class="pill pill-neutral">Not run yet</span>';
    if (!r.total) return '<span class="pill pill-neutral">No results</span>';
    if (r.passed === r.total) return '<span class="pill pill-pass">All passed</span>';
    return '<span class="pill pill-fail">' + EC.esc(r.passed + " of " + r.total + " passed") + "</span>";
  }

  function trayHtml(p) {
    var r = p.last_run;
    if (!r) {
      return '<div class="run-tray"><span class="run-tray-text">Last run: none yet</span>' +
        '<div class="progress progress-sm" aria-hidden="true"><div class="progress-fill" style="--p:0"></div></div></div>';
    }
    var parts = ["Run " + r.run_number];
    if (r.total) parts.push(r.passed + " of " + r.total + " passed");
    var d = shortDate(r.started_at);
    if (d) parts.push(d);
    var bar = "";
    if (r.total) {
      var frac = Math.max(0, Math.min(1, r.passed / r.total));
      bar = '<div class="progress progress-sm" role="progressbar" aria-label="Checks passed" aria-valuemin="0" aria-valuemax="' +
        Number(r.total) + '" aria-valuenow="' + Number(r.passed) + '"><div class="progress-fill ' +
        (r.passed === r.total ? "is-pass" : "is-fail") + '" style="--p:' + frac.toFixed(4) + '"></div></div>';
    }
    return '<div class="run-tray"><span class="run-tray-text">Last run: ' + EC.esc(parts.join(" · ")) + "</span>" + bar + "</div>";
  }

  function statsHtml(projects) {
    var latest = null;
    projects.forEach(function (p) {
      var t = p.last_run && p.last_run.started_at ? new Date(p.last_run.started_at) : null;
      if (t && !isNaN(t.getTime()) && (!latest || t > latest)) latest = t;
    });
    var when = latest ? shortDate(latest.toISOString()) : "No runs yet";
    return '<div class="stats enter" style="--i:1">' +
      '<div class="stat"><div><div class="stat-label">Projects</div><div class="stat-value">' + projects.length + '</div></div>' +
        '<span class="icon-tile"><i data-lucide="layout-grid" aria-hidden="true"></i></span></div>' +
      '<div class="stat"><div><div class="stat-label">Most recent run</div><div class="stat-value">' + EC.esc(when) + '</div></div>' +
        '<span class="icon-tile"><i data-lucide="history" aria-hidden="true"></i></span></div>' +
      "</div>";
  }

  function showList(projects) {
    var cards = projects.map(function (p, idx) {
      var href = "/project.html?id=" + encodeURIComponent(p.id);
      return '<li class="enter" style="--i:' + (idx + 2) + '"><article class="project-card" data-href="' + EC.esc(href) + '">' +
        '<div class="project-card-top"><span class="icon-tile"><i data-lucide="globe" aria-hidden="true"></i></span>' + statusPill(p) + "</div>" +
        '<div class="project-info"><h2 class="project-name">' + EC.esc(p.name) + "</h2>" +
          '<a class="project-link" href="' + EC.esc(p.site_url) + '" target="_blank" rel="noopener" title="' + EC.esc(p.site_url) + '">' +
          "<span>" + EC.esc(p.site_url) + '</span><i data-lucide="external-link" aria-hidden="true"></i></a></div>' +
        trayHtml(p) +
        '<div class="project-card-foot"><a class="btn btn-secondary btn-sm" href="' + EC.esc(href) + '" aria-label="Open ' + EC.esc(p.name) + '">Open<i data-lucide="chevron-right" aria-hidden="true"></i></a></div>' +
        "</article></li>";
    }).join("");
    var tile = '<li class="enter" style="--i:' + (projects.length + 2) + '"><button class="add-tile" id="add-tile" type="button">' +
      '<span class="add-tile-icon"><i data-lucide="plus" aria-hidden="true"></i></span>' +
      '<span class="add-tile-title">Add a website</span>' +
      '<span class="add-tile-help">Test another site as a phone and a laptop.</span></button></li>';
    content.innerHTML = statsHtml(projects) + '<ul class="project-grid">' + cards + tile + "</ul>";
    icons();
    Array.prototype.forEach.call(content.querySelectorAll(".project-card"), function (card) {
      card.addEventListener("click", function (ev) {
        if (ev.target.closest("a, button")) return;
        location.href = card.getAttribute("data-href");
      });
    });
    var at = document.getElementById("add-tile");
    at.addEventListener("click", function () { openForm(at); });
  }

  async function load() {
    showLoading();
    try {
      var data = await EC.api("GET", "/api/projects");
      var projects = (data && data.projects) || [];
      if (!projects.length) showEmpty(); else showList(projects);
    } catch (err) {
      showError(err && err.message ? err.message : "Something went wrong. Please try again.");
    }
  }

  // ---------- New project form (modal) ----------
  function openForm(opener) {
    var backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML =
      '<form class="modal stack" role="dialog" aria-modal="true" aria-labelledby="ns-title" novalidate>' +
        '<button class="icon-btn modal-close" type="button" id="ns-close" aria-label="Close" title="Close"><i data-lucide="x" aria-hidden="true"></i></button>' +
        '<div class="modal-head"><span class="eyebrow"><i data-lucide="globe" aria-hidden="true"></i>New site</span>' +
          '<h2 id="ns-title">Test a new website</h2><p>We\u2019ll test it as a phone and as a laptop.</p></div>' +
        '<div id="ns-banner" role="alert"></div>' +
        '<div class="field"><label class="label" for="ns-name">Project name</label>' +
          '<input class="input" id="ns-name" type="text" autocomplete="off" maxlength="80" placeholder="e.g. My Online Store">' +
          '<div class="error-msg" id="ns-name-err"></div></div>' +
        '<div class="field"><label class="label" for="ns-url">Website link</label>' +
          '<div class="input-wrap has-trail"><input class="input" id="ns-url" type="url" inputmode="url" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="https://yourstore.com" aria-describedby="ns-url-hint ns-url-err">' +
          '<span class="input-trail is-static" aria-hidden="true"><i data-lucide="link"></i></span></div>' +
          '<div class="hint" id="ns-url-hint"><i data-lucide="shield-check" aria-hidden="true"></i> Public link only. We never ask for passwords or keys.</div>' +
          '<div class="error-msg" id="ns-url-err"></div></div>' +
        '<div class="modal-actions"><button class="btn btn-ghost" type="button" id="ns-cancel">Cancel</button>' +
          '<button class="btn btn-primary" type="submit" id="ns-create"><i data-lucide="rocket" aria-hidden="true"></i>Create project</button></div>' +
      "</form>";
    document.body.appendChild(backdrop);
    icons();

    var form = backdrop.querySelector("form");
    var name = backdrop.querySelector("#ns-name");
    var url = backdrop.querySelector("#ns-url");
    var nameErr = backdrop.querySelector("#ns-name-err");
    var urlErr = backdrop.querySelector("#ns-url-err");
    var banner = backdrop.querySelector("#ns-banner");
    var create = backdrop.querySelector("#ns-create");
    var cancel = backdrop.querySelector("#ns-cancel");
    var closeX = backdrop.querySelector("#ns-close");
    var closing = false;
    var prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    name.focus();

    function close() {
      if (closing) return;
      closing = true;
      document.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = prevOverflow;
      if (opener && document.body.contains(opener)) opener.focus();
      // let the exit animation play (about 270ms), then remove
      backdrop.classList.add("is-closing");
      var removed = false;
      function done() { if (!removed) { removed = true; backdrop.remove(); } }
      backdrop.addEventListener("animationend", function (ev) { if (ev.target === backdrop) done(); });
      setTimeout(done, 400);
    }
    function onKey(ev) {
      if (ev.key === "Escape" && !create.disabled) { ev.preventDefault(); close(); return; }
      if (ev.key !== "Tab") return;
      var f = Array.prototype.filter.call(form.querySelectorAll("input, button:not(.input-trail)"), function (el) { return !el.disabled; });
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
    }
    document.addEventListener("keydown", onKey, true);
    cancel.addEventListener("click", close);
    closeX.addEventListener("click", function () { if (!create.disabled) close(); });
    backdrop.addEventListener("mousedown", function (ev) { if (ev.target === backdrop && !create.disabled) close(); });

    function setErr(input, el, msg) {
      input.classList.toggle("is-error", !!msg);
      if (msg) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid");
      el.textContent = msg || "";
    }

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (create.disabled) return;
      banner.innerHTML = "";
      var n = name.value.trim();
      var u = url.value.trim();
      setErr(name, nameErr, n ? "" : "Give your site a name, like Bubl Solar.");
      var urlOk = /^https?:\/\/[^\s/$.?#][^\s]*$/i.test(u);
      setErr(url, urlErr, urlOk ? "" : "The link needs to start with http:// or https://");
      if (!n) { name.focus(); return; }
      if (!urlOk) { url.focus(); return; }
      EC.busy(create, async function () {
        try {
          var res = await EC.api("POST", "/api/projects", { name: n, site_url: u });
          location.href = "/project.html?id=" + encodeURIComponent(res.id);
          await new Promise(function () {});
        } catch (err) {
          banner.innerHTML = '<div class="banner banner-error"><span class="banner-icon"><i data-lucide="circle-alert" aria-hidden="true"></i></span><div class="banner-body"><span>' +
            EC.esc(err && err.message ? err.message : "Something went wrong. Please try again.") + "</span></div></div>";
          icons();
        }
      }, "Creating…");
    });
  }

  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    var m = document.querySelector(".modal-backdrop"); if (m) { m.remove(); document.body.style.overflow = ""; }
    load();
  });
  load();
})();
