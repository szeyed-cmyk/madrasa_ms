document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('[data-print]').forEach(function (b) { b.addEventListener('click', function () { window.print(); }); });
  document.querySelectorAll('[data-close]').forEach(function (b) { b.addEventListener('click', function () { window.close(); }); });
  if (new URLSearchParams(location.search).get('autoprint') === '1') setTimeout(function () { window.print(); }, 300);
});
