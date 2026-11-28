/* 1.0.6 product tour player. Reads window.TOUR (tour-data.js). ?autostart=1 starts playing.
   Tooltip has Next / Back / Skip and "Step x of N". Bottom bar mirrors a video-style control strip. */
(function () {
  "use strict";
  var data = window.TOUR;
  if (!data || !data.steps || !data.steps.length) return;

  var CHAPTERS = data.chapters;
  var SCREENS = data.screens;
  var STEPS = data.steps;
  var BASE_MS = 4800;
  var i = 0;
  var playing = document.body.getAttribute("data-autostart") === "1";
  var speed = 1;
  var timer = null;

  function $(id) { return document.getElementById(id); }
  function playIcon() {
    var b = $("bPlay");
    b.innerHTML = playing
      ? '<svg width="18" height="18" fill="currentColor" aria-hidden="true"><rect x="4" y="3" width="3.5" height="12" rx="1"/><rect x="10.5" y="3" width="3.5" height="12" rx="1"/></svg>'
      : '<svg width="18" height="18" fill="currentColor" aria-hidden="true"><path d="M5 3l10 6-10 6z"/></svg>';
    b.setAttribute("aria-label", playing ? "Pause" : "Play");
  }

  Object.keys(SCREENS).forEach(function (k) { var im = new Image(); im.src = SCREENS[k].src; });

  $("segs").innerHTML = CHAPTERS.map(function () { return "<span><b></b></span>"; }).join("");
  $("list").innerHTML = CHAPTERS.map(function (c, k) {
    var idx = STEPS.findIndex(function (s) { return s.ch === k; });
    return '<button type="button" role="menuitem" data-go="' + idx + '"><em>' + (k + 1) + "</em>" + c + "</button>";
  }).join("");

  function layout(s) {
    var scr = SCREENS[s.screen];
    var shot = $("shot");
    if (shot.getAttribute("data-src") !== scr.src) {
      shot.style.opacity = "0";
      shot.setAttribute("data-src", scr.src);
      setTimeout(function () { shot.src = scr.src; shot.style.opacity = "1"; }, 160);
    }
    var bar = $("bar").offsetHeight || 88;
    var vh = window.innerHeight - bar;
    var vw = window.innerWidth;
    var scale = Math.min(vw / scr.w, 1.15);
    var box = s.box || [scr.w / 2 - 80, 160, 160, 80];
    var x = box[0], y = box[1], w = box[2], h = box[3];
    var maxOff = Math.max(0, scr.h * scale - vh);
    var want = h * scale > vh * 0.7 ? y * scale - 24 : (y + h / 2) * scale - vh * 0.42;
    var off = Math.min(maxOff, Math.max(0, want));
    shot.style.transform = "translateY(" + (-off) + "px) scale(" + scale + ")";
    var top = y * scale - off;
    return { x: x * scale, y: top, w: w * scale, h: Math.min(h * scale, vh - top - 8) };
  }

  function placePopup(r) {
    var pop = $("pop");
    var pw = pop.offsetWidth, ph = pop.offsetHeight;
    var bar = $("bar").offsetHeight || 88;
    var above = r.y - ph - 22 > 12;
    var below = r.y + r.h + 22 + ph < window.innerHeight - bar;
    var top;
    if (above) top = r.y - ph - 18;
    else top = below ? r.y + r.h + 18 : Math.max(12, window.innerHeight - bar - ph - 16);
    var left = Math.min(window.innerWidth - pw - 16, Math.max(16, r.x + r.w / 2 - pw * 0.25));
    pop.style.left = left + "px";
    pop.style.top = top + "px";
  }

  function show(n) {
    i = Math.max(0, Math.min(STEPS.length - 1, n));
    var s = STEPS[i];
    var r = layout(s);
    var last = i === STEPS.length - 1;
    var hole = $("hole");
    hole.hidden = false;
    hole.style.left = (r.x - 8) + "px";
    hole.style.top = (r.y - 8) + "px";
    hole.style.width = (r.w + 16) + "px";
    hole.style.height = (r.h + 16) + "px";
    $("ptag").textContent = (playing ? "Playing" : "Paused") + " · " + CHAPTERS[s.ch];
    $("ph").textContent = s.title;
    $("pp").textContent = s.body;
    $("pa").textContent = last ? "Tour complete" : "Look here";
    $("pop").hidden = false;
    placePopup(r);
    $("chap").textContent = (s.ch + 1) + ". " + CHAPTERS[s.ch];
    $("stepno").textContent = "Step " + (i + 1) + " of " + STEPS.length;
    $("bNext").textContent = last ? "Done" : "Next";
    $("bBack").disabled = i === 0;
    Array.prototype.forEach.call($("segs").children, function (seg, k) {
      var inCh = [];
      STEPS.forEach(function (t, idx) { if (t.ch === k) inCh.push(idx); });
      var done = inCh.filter(function (idx) { return idx <= i; }).length;
      seg.firstChild.style.width = (inCh.length ? (100 * done / inCh.length) : 0) + "%";
    });
    Array.prototype.forEach.call($("list").children, function (b, k) {
      b.classList.toggle("on", k === s.ch);
    });
    clearTimeout(timer);
    if (last) {
      playing = false;
      playIcon();
      $("ptag").textContent = "Tour complete";
    } else if (playing) {
      timer = setTimeout(function () { show(i + 1); }, BASE_MS / speed);
    }
  }

  function toggle() {
    playing = !playing;
    playIcon();
    show(i);
  }
  function closeTour() { window.location.href = "/"; }
  function skip() { closeTour(); }

  $("bPlay").addEventListener("click", function () {
    if (i === STEPS.length - 1 && !playing) { playing = true; playIcon(); show(0); }
    else toggle();
  });
  $("bNext").addEventListener("click", function () {
    if (i === STEPS.length - 1) closeTour();
    else { playing = false; playIcon(); show(i + 1); }
  });
  $("bBarNext").addEventListener("click", function () { playing = false; playIcon(); show(i + 1); });
  $("bBack").addEventListener("click", function () { playing = false; playIcon(); show(i - 1); });
  $("bPrev").addEventListener("click", function () { playing = false; playIcon(); show(i - 1); });
  $("bSkip").addEventListener("click", skip);
  $("bClose").addEventListener("click", closeTour);
  $("bReplay").addEventListener("click", function (e) {
    e.preventDefault();
    playing = true; playIcon(); show(0);
  });
  $("bSpeed").addEventListener("click", function () {
    speed = speed === 1 ? 1.5 : speed === 1.5 ? 2 : 1;
    $("bSpeed").textContent = speed + "×";
    show(i);
  });
  $("bList").addEventListener("click", function (e) {
    e.stopPropagation();
    $("list").hidden = !$("list").hidden;
  });
  $("list").addEventListener("click", function (e) {
    var b = e.target.closest("[data-go]");
    if (!b) return;
    $("list").hidden = true;
    playing = false; playIcon();
    show(parseInt(b.getAttribute("data-go"), 10));
  });
  document.addEventListener("click", function (e) {
    if (!e.target.closest("#list") && !e.target.closest("#bList")) $("list").hidden = true;
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === " " && !e.target.closest("button,a,input,select,textarea")) { e.preventDefault(); toggle(); }
    else if (e.key === "ArrowRight") { playing = false; playIcon(); show(i + 1); }
    else if (e.key === "ArrowLeft") { playing = false; playIcon(); show(i - 1); }
    else if (e.key === "Escape") closeTour();
  });
  window.addEventListener("resize", function () { show(i); });

  playIcon();
  var first = new Image();
  first.onload = first.onerror = function () { show(0); };
  first.src = SCREENS[STEPS[0].screen].src;
})();
