// Public landing page ("/"). Static: no API calls. It only looks in localStorage to see if the visitor is logged in.
(function () {
  var root = document.documentElement;

  // Logged in? -> "Dashboard" at the top and "Test yours" goes to the dashboard. Logged out -> Log in / Sign up.
  function applyAuth() {
    var inn = false;
    try { inn = !!(window.EC && EC.getSession()); } catch (e) { inn = false; }
    root.setAttribute("data-auth", inn ? "in" : "out");
    var ctas = document.querySelectorAll("[data-cta]");
    for (var i = 0; i < ctas.length; i++) ctas[i].setAttribute("href", inn ? "/home.html" : "/signup");
  }
  applyAuth();
  // Coming back with the Back button, or logging in / out in another tab.
  window.addEventListener("pageshow", function (e) { if (e.persisted) applyAuth(); });
  window.addEventListener("storage", applyAuth);

  if (window.lucide) window.lucide.createIcons();

  // Gentle fade-up for blocks as they scroll into view (transform + opacity only). No script, no hiding.
  var items = document.querySelectorAll(".lp-reveal");
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function show(el) { el.classList.add("is-in"); }
  if (!("IntersectionObserver" in window) || reduce) {
    for (var j = 0; j < items.length; j++) show(items[j]);
    root.classList.remove("js");
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { show(en.target); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    for (var k = 0; k < items.length; k++) io.observe(items[k]);
  }
})();
