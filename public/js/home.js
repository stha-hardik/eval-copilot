// Screen 2: Home, "My sites".
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
    var rows = "";
    for (var i = 0; i < 3; i++) rows += '<li><div class="skeleton" style="height:84px"></div></li>';
    content.innerHTML = '<ul class="list" aria-busy="true" aria-label="Loading your sites">' + rows + "</ul>";
  }

  function showError(msg) {
    content.innerHTML =
      '<div class="banner banner-error" role="alert"><i data-lucide="circle-alert" aria-hidden="true"></i>' +
      "<span>" + EC.esc(msg) + '</span><button class="btn btn-secondary btn-sm" id="retry" type="button">Try again</button></div>';
    icons();
    document.getElementById("retry").addEventListener("click", load);
  }

  function showEmpty() {
    content.innerHTML =
      '<div class="card empty"><i data-lucide="globe" aria-hidden="true"></i>' +
      '<h2 class="empty-title">No sites yet</h2>' +
      "<p>Add the live link of a site you want to test.</p>" +
      '<button class="btn btn-primary" id="first-site" type="button">Add your first site</button></div>';
    icons();
    var b = document.getElementById("first-site");
    b.addEventListener("click", function () { openForm(b); });
  }

  function lastRunText(p) {
    var r = p.last_run;
    if (!r) return "Not run yet";
    var parts = ["Run " + r.run_number];
    if (r.total) parts.push(r.passed + " of " + r.total + " passed");
    if (r.started_at) parts.push(EC.fmtDate(r.started_at));
    return parts.join(" · ");
  }

  function showList(projects) {
    var html = projects.map(function (p) {
      var href = "/project.html?id=" + encodeURIComponent(p.id);
      return '<li class="list-row is-clickable" data-href="' + EC.esc(href) + '">' +
        '<div class="list-row-main">' +
          '<div class="list-row-title truncate">' + EC.esc(p.name) + "</div>" +
          '<div class="list-row-meta small truncate" title="' + EC.esc(p.site_url) + '">' + EC.esc(p.site_url) + "</div>" +
          '<div class="list-row-meta">' + EC.esc(lastRunText(p)) + "</div>" +
        "</div>" +
        '<a class="btn btn-secondary" href="' + EC.esc(href) + '" aria-label="Open ' + EC.esc(p.name) + '">Open</a>' +
        "</li>";
    }).join("");
    content.innerHTML = '<ul class="list">' + html + "</ul>";
    Array.prototype.forEach.call(content.querySelectorAll(".list-row"), function (row) {
      row.addEventListener("click", function (ev) {
        if (ev.target.closest("a, button")) return;
        location.href = row.getAttribute("data-href");
      });
    });
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

  // ---------- New site form (modal) ----------
  function openForm(opener) {
    var backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML =
      '<form class="modal stack" role="dialog" aria-modal="true" aria-labelledby="ns-title" novalidate>' +
        '<div><h2 id="ns-title">New site</h2><p class="muted">Tell us which site to test.</p></div>' +
        '<div id="ns-banner" role="alert"></div>' +
        '<div class="field"><label class="label" for="ns-name">Name</label>' +
          '<input class="input" id="ns-name" type="text" autocomplete="off" maxlength="80" placeholder="Bubl Solar">' +
          '<div class="error-msg" id="ns-name-err"></div></div>' +
        '<div class="field"><label class="label" for="ns-url">Link to your live site</label>' +
          '<input class="input" id="ns-url" type="url" inputmode="url" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="https://yourstore.com" aria-describedby="ns-url-hint ns-url-err">' +
          '<div class="hint" id="ns-url-hint">Use the public link anyone can open. Never paste passwords or keys.</div>' +
          '<div class="error-msg" id="ns-url-err"></div></div>' +
        '<div class="modal-actions"><button class="btn btn-ghost" type="button" id="ns-cancel">Cancel</button>' +
          '<button class="btn btn-primary" type="submit" id="ns-create">Create</button></div>' +
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
    var prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    name.focus();

    function close() {
      document.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = prevOverflow;
      backdrop.remove();
      if (opener && document.body.contains(opener)) opener.focus();
    }
    function onKey(ev) {
      if (ev.key === "Escape" && !create.disabled) { ev.preventDefault(); close(); return; }
      if (ev.key !== "Tab") return;
      var f = Array.prototype.filter.call(form.querySelectorAll("input, button"), function (el) { return !el.disabled; });
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
    }
    document.addEventListener("keydown", onKey, true);
    cancel.addEventListener("click", close);
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
          banner.innerHTML = '<div class="banner banner-error"><i data-lucide="circle-alert" aria-hidden="true"></i><span>' +
            EC.esc(err && err.message ? err.message : "Something went wrong. Please try again.") + "</span></div>";
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
