/* 1.0.8: Demo sign-in cards and login password reveal (CSP-safe, no inline handlers, no Alpine).
   Plain ES5 in a static file so Chrome, Edge and Firefox on Windows all fill the same way.
   Click a card (or press Enter / Space on it) to fill #username and #password and show the
   password as text. "Sign in with this account" fills and submits the form. */
(function () {
  "use strict";

  function setInputValue(el, value) {
    if (!el) return;
    var desc = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
    if (desc && desc.set) desc.set.call(el, value);
    else el.value = value;
    el.defaultValue = value;
    try {
      el.setAttribute("value", value);
    } catch (err) {}
    el.dispatchEvent(new Event("input", { bubbles: true, cancelable: true }));
    el.dispatchEvent(new Event("change", { bubbles: true, cancelable: true }));
  }

  function revealPassword(pw) {
    if (!pw) return;
    try {
      pw.type = "text";
    } catch (err) {
      pw.setAttribute("type", "text");
    }
    var btn = document.querySelector("[data-password-toggle]");
    if (btn) btn.setAttribute("aria-label", "Hide password");
  }

  function fillFrom(start) {
    var user = document.getElementById("username");
    var pw = document.getElementById("password");
    setInputValue(user, start.getAttribute("data-demo-user") || "");
    revealPassword(pw);
    setInputValue(pw, start.getAttribute("data-demo-password") || "");
    return { user: user, pw: pw };
  }

  document.addEventListener("click", function (e) {
    var tog = e.target && e.target.closest ? e.target.closest("[data-password-toggle]") : null;
    if (tog) {
      e.preventDefault();
      var field = document.getElementById("password");
      if (!field) return;
      var show = field.type === "password";
      try {
        field.type = show ? "text" : "password";
      } catch (err) {
        field.setAttribute("type", show ? "text" : "password");
      }
      tog.setAttribute("aria-label", show ? "Hide password" : "Show password");
      return;
    }
    var start = e.target && e.target.closest ? e.target.closest("[data-demo-fill]") : null;
    if (!start) return;
    var fields = fillFrom(start);
    var signin = e.target.closest("[data-demo-signin]");
    if (signin && fields.user && fields.user.form) {
      e.preventDefault();
      if (typeof fields.user.form.requestSubmit === "function") fields.user.form.requestSubmit();
      else fields.user.form.submit();
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    if (e.target && e.target.closest && e.target.closest("[data-password-toggle]")) return;
    var start = e.target && e.target.closest ? e.target.closest("[data-demo-fill]") : null;
    if (!start) return;
    e.preventDefault();
    start.click();
  });
})();
