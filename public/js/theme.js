// Light / dark theme. Loaded in <head> (before the page draws) so there is no flash of the wrong theme.
// The reader's choice is kept in localStorage ("ec.theme" = "light" | "dark"); with no choice we follow the device.
(function () {
  var KEY = "ec.theme";
  function stored() { try { var t = localStorage.getItem(KEY); return t === "light" || t === "dark" ? t : null; } catch (e) { return null; } }
  function system() { return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; }
  function apply(t) {
    document.documentElement.setAttribute("data-theme", t);
    document.documentElement.style.colorScheme = t;
  }
  apply(stored() || system());
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var follow = function () { if (!stored()) { apply(system()); notify(); } };
    if (mq.addEventListener) mq.addEventListener("change", follow); else if (mq.addListener) mq.addListener(follow);
  }
  function notify() { try { document.dispatchEvent(new CustomEvent("ec:theme", { detail: { theme: current() } })); } catch (e) { /* old browsers */ } }
  function current() { return document.documentElement.getAttribute("data-theme") || "light"; }
  window.ECTheme = {
    get: current,
    set: function (t) {
      if (t !== "light" && t !== "dark") return;
      try { localStorage.setItem(KEY, t); } catch (e) { /* private mode: this page only */ }
      apply(t);
      notify();
    },
    toggle: function () { this.set(current() === "dark" ? "light" : "dark"); },
  };
})();
