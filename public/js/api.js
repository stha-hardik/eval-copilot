// Shared browser helper: session storage, the fetch wrapper for /api doors, and small UI helpers.
// Every page loads this first. Only the Supabase access + refresh tokens live in the browser, never a key.
(function () {
  const KEY = "evalcopilot.session";

  function getSession() {
    try { return JSON.parse(localStorage.getItem(KEY)) || null; } catch (e) { return null; }
  }
  function setSession(s) {
    try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* private mode: lives for this page only */ }
    memorySession = s;
  }
  function clearSession() {
    try { localStorage.removeItem(KEY); } catch (e) {}
    memorySession = null;
  }
  let memorySession = null;
  function current() { return getSession() || memorySession; }

  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  let refreshing = null;
  async function refresh() {
    const s = current();
    if (!s || !s.refresh_token) return false;
    if (!refreshing) {
      refreshing = fetch("/api/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: s.refresh_token }),
      }).then(async (r) => {
        if (!r.ok) return false;
        setSession(await r.json());
        return true;
      }).catch(() => false).finally(() => { setTimeout(() => { refreshing = null; }, 0); });
    }
    return refreshing;
  }

  // api("GET", "/api/projects") → parsed JSON. Throws ApiError with a plain-words message.
  // On 401 it refreshes the session once and retries; if that fails it sends the user to the login page.
  async function api(method, path, body, retried) {
    const s = current();
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (s && s.access_token) headers["Authorization"] = "Bearer " + s.access_token;
    let r;
    try {
      r = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch (e) {
      throw new ApiError(0, "We couldn't reach the server. Check your internet and try again.");
    }
    if (r.status === 401 && !retried && !path.startsWith("/api/login") && !path.startsWith("/api/signup")) {
      if (await refresh()) return api(method, path, body, true);
      clearSession();
      location.href = "/login?next=" + encodeURIComponent(location.pathname + location.search);
      throw new ApiError(401, "Please log in again.");
    }
    let data = null;
    const text = await r.text();
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
    if (!r.ok) {
      let msg = data && data.detail;
      if (Array.isArray(msg)) msg = "Some details are missing or not valid.";
      if (!msg) msg = r.status >= 500 ? "Something went wrong on our side. Please try again." : "That didn't work. Please try again.";
      throw new ApiError(r.status, msg);
    }
    return data;
  }

  // Pages that need a login call requireLogin() first.
  function requireLogin() {
    if (!current()) {
      location.href = "/login?next=" + encodeURIComponent(location.pathname + location.search);
      return false;
    }
    return true;
  }

  function logout() {
    clearSession();
    location.href = "/";
  }

  function param(name) {
    return new URLSearchParams(location.search).get(name);
  }

  // Escape text before putting it into innerHTML.
  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // toast("Saved", "success" | "error" | "info")
  function toast(message, kind) {
    let box = document.getElementById("toasts");
    if (!box) {
      box = document.createElement("div");
      box.id = "toasts";
      box.className = "toasts";
      box.setAttribute("role", "status");
      box.setAttribute("aria-live", "polite");
      document.body.appendChild(box);
    }
    const t = document.createElement("div");
    t.className = "toast toast-" + (kind || "info");
    t.textContent = message;
    box.appendChild(t);
    setTimeout(() => { t.classList.add("toast-out"); }, 3600);
    setTimeout(() => { t.remove(); }, 4000);
  }

  // Grey out a button while work runs: await busy(btn, async () => {...}, "Saving…")
  async function busy(btn, fn, label) {
    const old = btn.innerHTML;
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    if (label) btn.innerHTML = '<span class="spinner" aria-hidden="true"></span>' + esc(label);
    try { return await fn(); } finally {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
      btn.innerHTML = old;
      if (window.lucide) window.lucide.createIcons();
    }
  }

  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) +
      ", " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }

  window.EC = { api, ApiError, getSession: current, setSession, clearSession, requireLogin, logout, param, esc, toast, busy, fmtDate };
})();
