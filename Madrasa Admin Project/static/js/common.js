/* Shared helpers: API calls with CSRF token + readable errors, toasts, formatting. */
(function () {
  const meta = (n) => (document.querySelector(`meta[name="${n}"]`) || {}).content || '';

  async function api(url, options = {}) {
    const opts = { method: 'GET', credentials: 'same-origin', ...options };
    opts.headers = { 'Accept': 'application/json', ...(options.headers || {}) };
    if (opts.method !== 'GET') opts.headers['X-CSRF-Token'] = meta('csrf-token');
    if (opts.body === null || opts.body === undefined) delete opts.body;
    else if (!(opts.body instanceof FormData) && typeof opts.body !== 'string') {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    let res;
    try {
      res = await fetch(url, opts);
    } catch (e) {
      throw new Error('Cannot reach the server. Is it running?');
    }
    if (res.status === 401) { window.location.href = '/login'; throw new Error('Session expired. Please log in again.'); }
    const type = res.headers.get('content-type') || '';
    const data = type.includes('application/json') ? await res.json() : await res.text();
    if (!res.ok) {
      let msg = (data && data.detail) || data || ('Request failed (' + res.status + ')');
      if (typeof msg !== 'string') msg = JSON.stringify(msg);
      if (res.status === 403 && msg.includes('Password change required')) window.location.href = '/change-password';
      throw new Error(msg);
    }
    return data;
  }

  // 1.0.5: interface text in the visitor's language (catalogue embedded by templates/_base.html).
  let I18N = null;
  function t(key, fallback) {
    if (I18N === null) {
      try { I18N = JSON.parse((document.getElementById('i18n-data') || {}).dataset?.json || '{}'); } catch (e) { I18N = {}; }
    }
    return I18N[key] || fallback || key;
  }

  const TOAST_ICONS = {
    ok: '<path d="m8 12 3 3 5-6"/><circle cx="12" cy="12" r="9"/>',
    error: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
    warn: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>',
  };
  function toast(message, kind = 'ok') {
    let box = document.getElementById('toast-box');
    if (!box) {
      box = document.createElement('div');
      box.id = 'toast-box';
      box.className = 'pointer-events-none fixed bottom-4 end-4 start-4 sm:start-auto z-[80] flex flex-col items-end gap-2 no-print';
      box.setAttribute('aria-live', 'polite');
      document.body.appendChild(box);
    }
    const el = document.createElement('div');
    const tone = kind === 'error' ? 'border-red-200' : kind === 'warn' ? 'border-amber-200' : 'border-emerald-200';
    const iconTone = kind === 'error' ? 'text-red-600 bg-red-50' : kind === 'warn' ? 'text-amber-600 bg-amber-50' : 'text-emerald-600 bg-emerald-50';
    el.className = 'toast ' + tone;
    el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    el.dataset.toast = kind;
    const icon = document.createElement('span');
    icon.className = 'flex h-8 w-8 shrink-0 items-center justify-center rounded-full ' + iconTone;
    icon.innerHTML = '<svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (TOAST_ICONS[kind] || TOAST_ICONS.ok) + '</svg>';
    const text = document.createElement('span');
    text.className = 'flex-1 pt-1.5 leading-snug';
    text.textContent = message;  // never innerHTML for messages
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'shrink-0 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600';
    close.setAttribute('aria-label', t('common.close', 'Close'));
    close.innerHTML = '<svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>';
    close.onclick = () => el.remove();
    el.append(icon, text, close);
    box.appendChild(el);
    setTimeout(() => el.remove(), kind === 'error' ? 7000 : 3500);
  }

  // 1.0.5: display currency (topbar switcher). Amounts are stored in the default currency; another
  // currency only changes what is shown (amount x rate from Settings > Currencies).
  let CURRENCIES = null;
  function currencies() {
    if (CURRENCIES === null) {
      try { CURRENCIES = JSON.parse((document.getElementById('i18n-data') || {}).dataset?.currencies || '[]'); } catch (e) { CURRENCIES = []; }
    }
    return CURRENCIES;
  }
  function displayCurrency() {
    let code = null;
    try { code = localStorage.getItem('ma.currency'); } catch (e) { /* private mode */ }
    const list = currencies();
    const sel = list.find(c => c.code === code);
    return sel && !sel.is_default ? sel : null;
  }
  function setDisplayCurrency(code) {
    try { localStorage.setItem('ma.currency', code); } catch (e) { /* ignore */ }
  }
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-currency-switch]').forEach((sel) => {
      const d = displayCurrency();
      const def = currencies().find(c => c.is_default);
      sel.value = d ? d.code : (def ? def.code : sel.value);
      sel.addEventListener('change', () => { setDisplayCurrency(sel.value); location.reload(); });
    });
  });

  function money(v, cur) {
    let n = Number(v || 0);
    let digits = 2;
    const d = displayCurrency();
    if (d) { n = n * (Number(d.rate) || 1); cur = d.symbol; digits = d.decimals ?? 2; }
    const sym = cur || '৳';
    return sym + (sym.length > 1 ? ' ' : '') + n.toLocaleString('en-US', { maximumFractionDigits: digits });
  }

  // 1.0.5 charts (dashboard): SVG paths for a 0-100 series, short month / day labels.
  function points(values, w, h) {
    const n = values.length;
    const pad = 8;
    return values.map((v, i) => [n > 1 ? (i * w) / (n - 1) : w / 2, pad + (h - 2 * pad) * (1 - Math.max(0, Math.min(100, Number(v) || 0)) / 100)]);
  }
  function linePath(values, w, h) {
    const p = points(values, w, h);
    if (!p.length) return '';
    let d = 'M' + p[0][0].toFixed(1) + ' ' + p[0][1].toFixed(1);
    for (let i = 1; i < p.length; i++) {
      const [x0, y0] = p[i - 1]; const [x1, y1] = p[i]; const cx = (x0 + x1) / 2;
      d += ' C' + cx.toFixed(1) + ' ' + y0.toFixed(1) + ' ' + cx.toFixed(1) + ' ' + y1.toFixed(1) + ' ' + x1.toFixed(1) + ' ' + y1.toFixed(1);
    }
    return d;
  }
  function areaPath(values, w, h) {
    const line = linePath(values, w, h);
    return line ? line + ' L' + w + ' ' + h + ' L0 ' + h + ' Z' : '';
  }
  function locale() { return document.documentElement.lang || undefined; }
  function monthShort(ym) {
    const d = new Date((ym || '') + '-01T00:00');
    return Number.isNaN(d.getTime()) ? ym : d.toLocaleDateString(locale(), { month: 'short' });
  }
  function dayShort(iso) {
    const d = new Date((iso || '') + 'T00:00');
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(locale(), { day: 'numeric', month: 'short' });
  }

  function today() {
    const d = new Date();
    const pad = (x) => String(x).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function gradeClass(g) {
    if (!g || g === '-') return 'bg-slate-100 text-slate-500';
    if (g === 'F') return 'bg-red-100 text-red-700';
    if (g.startsWith('A')) return 'bg-emerald-100 text-emerald-700';
    if (g.startsWith('B')) return 'bg-sky-100 text-sky-700';
    return 'bg-amber-100 text-amber-700';
  }

  function statusClass(s) {
    return ({ Active: 'bg-emerald-100 text-emerald-700', Inactive: 'bg-slate-200 text-slate-600',
      Transferred: 'bg-sky-100 text-sky-700', Graduated: 'bg-violet-100 text-violet-700',
      Archived: 'bg-red-100 text-red-700', Pass: 'bg-emerald-100 text-emerald-700', Fail: 'bg-red-100 text-red-700',
      Incomplete: 'bg-amber-100 text-amber-700' })[s] || 'bg-slate-100 text-slate-600';
  }


  // Colour per subject on the routine grid (classes kept literal so Tailwind includes them).
  const SUBJECT_COLORS = [
    'bg-emerald-50 border-emerald-200 text-emerald-900', 'bg-sky-50 border-sky-200 text-sky-900',
    'bg-violet-50 border-violet-200 text-violet-900', 'bg-amber-50 border-amber-200 text-amber-900',
    'bg-rose-50 border-rose-200 text-rose-900', 'bg-teal-50 border-teal-200 text-teal-900',
    'bg-indigo-50 border-indigo-200 text-indigo-900', 'bg-lime-50 border-lime-200 text-lime-900',
    'bg-orange-50 border-orange-200 text-orange-900', 'bg-cyan-50 border-cyan-200 text-cyan-900',
  ];
  function subjectColor(id) { return SUBJECT_COLORS[Math.abs(Number(id) || 0) % SUBJECT_COLORS.length]; }

  // Server times are UTC ("...Z"); show them in the browser's local time.
  function when(v) {
    if (!v) return '';
    if (!String(v).includes('T')) return v;
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return v;
    const mins = Math.round((Date.now() - d.getTime()) / 60000);
    if (mins < 1) return t('time.just_now', 'just now');
    if (mins < 60) return mins + ' ' + t('time.min_ago', 'min ago');
    if (mins < 24 * 60) return Math.round(mins / 60) + ' ' + t('time.h_ago', 'h ago');
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  }

  function greeting() {
    const h = new Date().getHours();
    return h < 12 ? t('dash.good_morning', 'Good morning') : h < 17 ? t('dash.good_afternoon', 'Good afternoon') : t('dash.good_evening', 'Good evening');
  }

  // Shared routine state/helpers for the admin app and the student portal.
  function routineMixin() {
    return {
      rt: { days: [], day_names: {}, periods: [], slots: [], today: '' },
      rtDay: '', rtMode: 'class', rtEditable: false,
      rtIndex: {},
      rtSet(data, mode, editable) {
        this.rt = { days: data.days || [], day_names: data.day_names || {}, periods: data.periods || [], slots: data.slots || [], today: data.today || '' };
        const idx = {};
        this.rt.slots.forEach(s => { idx[s.day + ':' + s.period_id] = s; });
        this.rtIndex = idx;
        this.rtMode = mode;
        this.rtEditable = !!editable;
        if (!this.rt.days.includes(this.rtDay)) this.rtDay = this.rt.days.includes(this.rt.today) ? this.rt.today : (this.rt.days[0] || '');
      },
      rtCell(day, periodId) { return this.rtIndex[day + ':' + periodId] || null; },
      rtClick() {},
    };
  }

  // 1.3.0: readable temporary password (no 0/O, 1/l/I), always with letters and digits
  function genPassword(len = 10) {
    const abc = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789';
    for (;;) {
      const buf = new Uint32Array(len);
      crypto.getRandomValues(buf);
      const pw = Array.from(buf, (n) => abc[n % abc.length]).join('');
      if (/\d/.test(pw) && /[a-z]/i.test(pw)) return pw;
    }
  }
  // 1.3.0: printable credentials slips (shown once) — opens a print window with cut-out cards

  // ---- form blanks shared by the admin mixins
  const blank = {
    student: () => ({ name: '', student_id: '', class_id: '', section_id: '', roll_no: '', admission_no: '', photo: '',
      admission_date: today(), dob: '', gender: '', status: 'Active', guardian_name: '', guardian_relation: 'Father',
      guardian_phone: '', address: '', notes: '', apply_class_subjects: true }),
    subject: () => ({ name: '', code: '', max_marks: 100, pass_marks: 33, credits: 3, is_active: true, class_ids: [] }),
    teacher: () => ({ full_name: '', username: '', phone: '', password: '', photo: '' }),
  };
  const thisMonth = () => today().slice(0, 7);

  // ---- credential slips: ONE row builder for the admin app (teachers, student logins, bulk) and the student page
  function studentExtra(s) {
    return 'ID ' + (s.student_id || '') + ' · ' + (s.class_name || '') + ' - ' + (s.section_name || '') + (s.roll_no != null ? ' · Roll ' + s.roll_no : '');
  }
  function credRow(name, username, password, extra) { return { name: name || username, username, password: password || '', extra: extra || '' }; }
  // Raw API rows ({name|full_name, username, password|temporary_password, student_id, class_name, ...}) -> slip rows.
  function credRows(apiRows, kind) {
    return (apiRows || []).map((x) => credRow(x.name || x.full_name, x.username, x.password || x.temporary_password, kind === 'teacher' ? 'Teacher' : studentExtra(x)));
  }
  function printSlips(title, school, rows) {
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
    const url = location.origin + '/login';
    const cards = rows.map((r) => `<div class="slip"><div class="sch">${esc(school)}</div><div class="nm">${esc(r.name)}</div>` +
      `<div class="ex">${esc(r.extra || '')}</div><table><tr><td>Login page</td><td>${esc(url)}</td></tr>` +
      `<tr><td>Username</td><td><b>${esc(r.username)}</b></td></tr><tr><td>Temporary password</td><td><b>${esc(r.password)}</b></td></tr></table>` +
      '<div class="nt">You must choose a new password at first login. Keep it private.</div></div>').join('');
    const w = window.open('', '_blank');
    if (!w) { toast('Allow pop-ups to print the slips', 'warn'); return; }
    w.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${esc(title)}</title><style>
      body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:16px;color:#0f172a}h1{font-size:16px;margin:0 0 12px}
      .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.slip{border:1px dashed #64748b;border-radius:8px;padding:10px 12px;break-inside:avoid}
      .sch{font-size:11px;color:#047857;font-weight:700;text-transform:uppercase;letter-spacing:.04em}.nm{font-weight:700;font-size:15px;margin-top:2px}
      .ex{font-size:11px;color:#475569;margin-bottom:6px}table{font-size:12px;border-collapse:collapse}td{padding:2px 8px 2px 0;vertical-align:top}
      td:first-child{color:#64748b}b{font-family:ui-monospace,Consolas,monospace;font-size:14px}.nt{font-size:10px;color:#64748b;margin-top:6px}
      @media print{body{margin:8mm}h1{display:none}}</style></head><body><h1>${esc(title)}</h1><div class="grid">${cards}</div></body></html>`);
    w.document.close();
    w.focus();
    setTimeout(() => w.print(), 300);
  }
  function downloadCsv(filename, header, rows) {
    const cell = (v) => { let t = String(v ?? ''); if (/^[=+\-@\t\r]/.test(t)) t = "'" + t; return '"' + t.replace(/"/g, '""') + '"'; };
    const text = '\ufeff' + [header, ...rows].map((r) => r.map(cell).join(',')).join('\r\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
    a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  // CSP-safe auto-submit (no inline handlers): <select data-autosubmit> submits its form on change.
  document.addEventListener('change', (e) => { const el = e.target; if (el && el.matches && el.matches('[data-autosubmit]') && el.form) el.form.submit(); });

  window.MA = { t, currencies, displayCurrency, linePath, areaPath, monthShort, dayShort, api, toast, money, today, gradeClass, statusClass, meta, subjectColor, when, greeting, routineMixin, genPassword, printSlips, downloadCsv, blank, thisMonth, credRow, credRows, studentExtra, mixins: {} };
})();
