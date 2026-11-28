/* 1.0.6 landing: scroll-reveal and sticky-nav helper. CSP-safe, no inline handlers. */
(function () {
  "use strict";
  var nodes = document.querySelectorAll("[data-reveal]");
  if (!nodes.length) return;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    nodes.forEach(function (el) { el.classList.add("is-in"); });
    return;
  }
  if (!("IntersectionObserver" in window)) {
    nodes.forEach(function (el) { el.classList.add("is-in"); });
    return;
  }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) {
        e.target.classList.add("is-in");
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" });
  nodes.forEach(function (el) { io.observe(el); });
})();
