// Log in / sign up screen. One page, two routes: /login and /signup (or ?mode=signup).
(function () {
  // Someone who is already logged in has nothing to do here: straight to their dashboard.
  if (EC.getSession()) { location.replace("/home.html"); return; }

  var mode = "login";
  var form = document.getElementById("auth-form");
  var email = document.getElementById("email");
  var password = document.getElementById("password");
  var emailErr = document.getElementById("email-error");
  var passErr = document.getElementById("password-error");
  var hint = document.getElementById("password-hint");
  var banner = document.getElementById("form-banner");
  var submit = document.getElementById("submit");
  var submitLabel = document.getElementById("submit-label");
  var eye = document.getElementById("toggle-password");
  var segEl = document.querySelector(".segmented");
  var seg = EC.ui.segmented(segEl);
  var switchText = document.getElementById("switch-text");
  var switchLink = document.getElementById("switch-link");

  function icons() { if (window.lucide) window.lucide.createIcons(); }

  function wantsSignup() {
    return /^\/signup\/?$/.test(location.pathname) || EC.param("mode") === "signup";
  }

  // Keep the address bar in step with the mode, so a refresh or a shared link opens the same form.
  function updateUrl(next) {
    try {
      var url = new URL(location.href);
      if (/^\/(login|signup)\/?$/.test(url.pathname)) {
        url.pathname = next === "signup" ? "/signup" : "/login";
      } else if (next === "signup") {
        url.searchParams.set("mode", "signup");
      } else {
        url.searchParams.delete("mode");
      }
      history.replaceState(null, "", url.pathname + url.search + url.hash);
    } catch (e) { /* the form still works without it */ }
  }

  function setMode(next, instant) {
    mode = next;
    seg.select(next, { silent: true, instant: !!instant }); // the sliding indicator and aria-pressed live in EC.ui.segmented
    switchText.textContent = next === "signup" ? "Already have an account?" : "New here?";
    switchLink.textContent = next === "signup" ? "Log in" : "Sign up";
    var keep = EC.param("next");
    switchLink.setAttribute("href", (next === "signup" ? "/login" : "/signup") + (keep ? "?next=" + encodeURIComponent(keep) : ""));
    hint.hidden = next !== "signup";
    password.setAttribute("autocomplete", next === "signup" ? "new-password" : "current-password");
    submitLabel.textContent = next === "signup" ? "Create account" : "Log in";
    document.title = (next === "signup" ? "Sign up" : "Log in") + " · Eval Co-pilot";
    clearErrors();
  }

  function clearErrors() {
    banner.innerHTML = "";
    emailErr.textContent = "";
    passErr.textContent = "";
    email.classList.remove("is-error");
    password.classList.remove("is-error");
  }

  // Title line plus an optional plain explanation.
  function showBanner(msg, detail) {
    banner.innerHTML = '<div class="banner banner-error"><span class="banner-icon"><i data-lucide="circle-alert" aria-hidden="true"></i></span>' +
      '<div class="banner-body"><span class="banner-title">' + EC.esc(msg) + "</span>" +
      (detail ? "<span>" + EC.esc(detail) + "</span>" : "") + "</div></div>";
    icons();
  }

  eye.addEventListener("click", function () {
    var show = password.type === "password";
    password.type = show ? "text" : "password";
    eye.setAttribute("aria-pressed", String(show));
    eye.setAttribute("aria-label", show ? "Hide password" : "Show password");
    eye.title = show ? "Hide password" : "Show password";
    eye.innerHTML = '<i data-lucide="' + (show ? "eye-off" : "eye") + '" aria-hidden="true"></i>';
    icons();
  });
  icons();

  function fieldError(input, msgEl, msg) {
    input.classList.add("is-error");
    input.setAttribute("aria-invalid", "true");
    msgEl.textContent = msg;
  }

  function validate() {
    clearErrors();
    email.removeAttribute("aria-invalid");
    password.removeAttribute("aria-invalid");
    var ok = true;
    var e = email.value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)) {
      fieldError(email, emailErr, "Enter your email, like you@yourstore.com.");
      ok = false;
    }
    if (!password.value) {
      fieldError(password, passErr, "Enter your password.");
      ok = false;
    } else if (mode === "signup" && password.value.length < 8) {
      fieldError(password, passErr, "Use at least 8 characters.");
      ok = false;
    }
    if (!ok) (email.classList.contains("is-error") ? email : password).focus();
    return ok;
  }

  function nextUrl() {
    var n = EC.param("next");
    return n && n.charAt(0) === "/" && n.charAt(1) !== "/" && n.charAt(1) !== "\\" ? n : "/home.html";
  }

  window.addEventListener("pageshow", function (e) { if (e.persisted) location.reload(); });

  segEl.addEventListener("change", function (ev) { setMode(ev.detail.value); updateUrl(ev.detail.value); });

  // "Already have an account? Log in" / "New here? Sign up": a real link that also works without scripts.
  switchLink.addEventListener("click", function (ev) {
    ev.preventDefault();
    var next = mode === "signup" ? "login" : "signup";
    setMode(next);
    updateUrl(next);
  });

  if (wantsSignup()) setMode("signup", true);
  else setMode("login", true);

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (submit.disabled || !validate()) return;
    var body = { email: email.value.trim(), password: password.value };
    var path = mode === "signup" ? "/api/signup" : "/api/login";
    EC.busy(submit, async function () {
      try {
        var session = await EC.api("POST", path, body);
        EC.setSession(session);
        location.href = nextUrl();
        await new Promise(function () {}); // stay greyed out while the page changes
      } catch (err) {
        if (err instanceof EC.ApiError) {
          if (err.status === 401) showBanner("That email and password don't match.", "Check what you typed and try again.");
          else if (err.status === 409 && mode === "signup") showBanner("Check your email to confirm your account, then log in.");
          else showBanner(err.message);
        } else {
          showBanner("Something went wrong. Please try again.");
        }
      }
    }, mode === "signup" ? "Creating account…" : "Logging in…");
  });
})();
