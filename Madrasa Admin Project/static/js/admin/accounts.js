/* Admin app mixin: Teachers page, student logins page and the credentials slip dialog (admin).
   Merged into adminApp() by static/js/app.js; methods use `this` = the Alpine component. */
window.MA.mixins = window.MA.mixins || {};
window.MA.mixins.accounts = () => ({
    // ---------- teachers (1.3.0)
    async loadTeachers() { this.teacherRows = await MA.api('/api/teachers/manage'); },
    filteredTeachers() {
      const q = this.teacherQ.trim().toLowerCase();
      if (!q) return this.teacherRows;
      return this.teacherRows.filter(t => [t.full_name, t.username, t.phone, ...t.assignments.map(a => a.subject_name + ' ' + a.class_name)]
        .some(v => (v || '').toLowerCase().includes(q)));
    },
    teacherGroups(t) {
      // one line per subject: "Math  Grade 1, Grade 2 - A, ..." (keeps long assignment lists short)
      const by = {};
      for (const a of t.assignments) (by[a.subject_name] = by[a.subject_name] || []).push(a.class_name + (a.section_name ? ' - ' + a.section_name : ''));
      const nat = (x, y) => x.localeCompare(y, undefined, { numeric: true });
      return Object.keys(by).sort(nat).map(k => ({ subject: k, classes: [...new Set(by[k])].sort(nat).join(', ') }));
    },
    teacherBadge(t) {
      if (!t.has_password) return { text: 'No password yet', cls: 'bg-slate-100 text-slate-600' };
      if (!t.is_active) return { text: 'Disabled', cls: 'bg-red-100 text-red-700' };
      if (t.must_change_password) return { text: 'First login pending', cls: 'bg-amber-100 text-amber-800' };
      return { text: 'Active', cls: 'bg-emerald-100 text-emerald-700' };
    },
    openTeacherForm(t) {
      this.tForm = t ? { open: true, id: t.id, show: false, touched: true, d: { full_name: t.full_name, username: t.username, phone: t.phone || '', password: '', photo: t.photo || '' } }
        : { open: true, id: null, show: false, touched: false, d: MA.blank.teacher() };
      this.$nextTick(() => { const el = document.getElementById('tf-name'); if (el) el.focus(); });
    },
    suggestUsername() {
      if (this.tForm.id || this.tForm.touched) return;
      this.tForm.d.username = (this.tForm.d.full_name || '').toLowerCase().normalize('NFKD').replace(/[^a-z0-9 ]/g, '').trim().split(/\s+/).filter(Boolean).slice(0, 2).join('.').slice(0, 64);
    },
    async saveTeacher() {
      const f = this.tForm;
      const body = { full_name: f.d.full_name, username: f.d.username, phone: f.d.phone || null, photo: f.d.photo || null };
      if (!f.id) body.password = f.d.password || null;
      const r = await this.run(() => MA.api(f.id ? '/api/teachers/' + f.id : '/api/teachers', { method: f.id ? 'PUT' : 'POST', body }), f.id ? 'Teacher updated' : 'Teacher added');
      if (!r) return;
      this.tForm.open = false;
      this.teachers = [];  // refresh the routine page's teacher list next time
      if (!f.id) this.showCred('New teacher login', MA.credRows([{ full_name: body.full_name, username: r.username, password: r.temporary_password || f.d.password }], 'teacher'));
      await this.loadTeachers();
    },
    async resetTeacherPassword(t) {
      if (!confirm(`Give ${t.full_name || t.username} a new temporary password? Their current password stops working.`)) return;
      const r = await this.run(() => MA.api(`/api/teachers/${t.id}/reset-password`, { method: 'POST', body: {} }), 'New temporary password created');
      if (r) { this.showCred('Teacher password reset', MA.credRows([{ full_name: t.full_name || t.username, username: r.username, password: r.temporary_password }], 'teacher')); await this.loadTeachers(); }
    },
    async toggleTeacher(t) {
      if (!t.is_active && !t.has_password) return MA.toast('Set a password first — the login is enabled with it.', 'warn');
      if (t.is_active && !confirm(`Disable the login of ${t.full_name || t.username}? They are logged out at once.`)) return;
      if (await this.run(() => MA.api(`/api/teachers/${t.id}/status`, { method: 'POST', body: { is_active: !t.is_active } }), t.is_active ? 'Login disabled' : 'Login enabled')) await this.loadTeachers();
    },
    goAssign(t) {
      this.rtTab = 'assign';
      this.asgFilter = { class_id: '', teacher_id: t ? t.id : '' };
      this.newAsg = { teacher_id: t ? t.id : '', class_id: '', section_id: '', subject_id: '' };
      this.teachers = [];
      location.hash = 'routine';
    },

    // ---------- student logins (1.3.0)
    async loadLogins() {
      const qs = new URLSearchParams({ class_id: this.lg.class_id || 0, section_id: this.lg.section_id || 0, q: this.lg.q });
      this.loginRows = await MA.api('/api/student-logins?' + qs);
    },
    loginBadge(r) {
      if (!r.has_login) return { text: 'No login', cls: 'bg-slate-100 text-slate-600' };
      if (!r.is_active) return { text: 'Disabled', cls: 'bg-red-100 text-red-700' };
      if (r.must_change) return { text: 'First login pending', cls: 'bg-amber-100 text-amber-800' };
      return { text: 'Active', cls: 'bg-emerald-100 text-emerald-700' };
    },
    async studentLogin(r) {
      if (r.has_login && !confirm(`Give ${r.name} a new temporary password? The current one stops working.`)) return;
      const res = await this.run(() => MA.api(`/api/students/${r.id}/create-login`, { method: 'POST', body: {} }), r.has_login ? 'New temporary password created' : 'Login created');
      if (res) { this.showCred('Student login', MA.credRows([{ ...r, username: res.username, password: res.temporary_password }], 'student')); await this.loadLogins(); }
    },
    async toggleStudentLogin(r) {
      const url = `/api/students/${r.id}/${r.is_active ? 'disable' : 'enable'}-login`;
      if (await this.run(() => MA.api(url, { method: 'POST' }), r.is_active ? 'Login disabled' : 'Login enabled')) await this.loadLogins();
    },
    async bulkLogins() {
      const c = this.className(this.lg.class_id);
      const sec = this.lg.section_id ? ' - ' + (this.sectionsOf(this.lg.class_id).find(x => x.id == this.lg.section_id) || {}).name : '';
      if (!confirm(`Create logins for every student of ${c}${sec} who has none${this.lg.reset_existing ? ', and reset the others' : ''}?`)) return;
      const body = { class_id: Number(this.lg.class_id), section_id: this.lg.section_id ? Number(this.lg.section_id) : null, reset_existing: !!this.lg.reset_existing };
      const r = await this.run(() => MA.api('/api/student-logins/bulk', { method: 'POST', body }), (x) => `${x.created} login(s) created` + (x.reset ? `, ${x.reset} reset` : ''));
      if (!r) return;
      this.showCred(`Student logins — ${c}${sec}`, MA.credRows(r.credentials, 'student'), r.skipped);
      this.lg.reset_existing = false;
      await this.loadLogins();
    },
    showCred(title, rows, skipped) { this.cred = { open: true, title, rows: rows || [], skipped: skipped || [] }; },
    closeCred() {
      if (this.cred.rows.length && !confirm('Close? The passwords cannot be shown again (you can reset them later).')) return;
      this.cred = { open: false, title: '', rows: [], skipped: [] };
    },
    printCred() { MA.printSlips(this.cred.title, this.school.name, this.cred.rows); },
    downloadCred() {
      MA.downloadCsv('logins-' + MA.today() + '.csv', ['name', 'details', 'username', 'temporary_password'], this.cred.rows.map(r => [r.name, r.extra || '', r.username, r.password]));
    },
});
