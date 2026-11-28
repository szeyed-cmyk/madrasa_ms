/* Student profile hub: details, subjects & marks, attendance, fees, login. */
function studentProfile() {
  const thisMonth = () => MA.today().slice(0, 7);
  return {
    ...MA.routineMixin(),
    MA: window.MA,
    role: document.body.dataset.role,
    id: Number(document.body.dataset.student),
    get staff() { return this.role === 'admin' || this.role === 'teacher'; },
    navOpen: false, busy: false, loading: true, editing: false, tab: 'overview', exam_id: '',
    d: { id: null, subjects: [], exams: [], result: { gpa: 0, subjects_marked: 0 }, attendance: { counts: {}, recent: [], percentage: null }, payments: [], class_default_subject_ids: [] },
    f: {}, classes: [], allSubjects: [], addSubjId: '', tempPassword: '', tempUser: '',
    loginForm: { username: '', password: '' },
    payForm: { amount: '', fee_month: thisMonth(), fee_head: 'Monthly Tuition', method: 'Cash', note: '' },

    tabs() {
      const t = [{ id: 'overview', label: MA.t('student.tab_overview', 'Overview') }, { id: 'subjects', label: MA.t('student.tab_subjects', 'Subjects & Marks') }, { id: 'attendance', label: MA.t('nav.attendance', 'Attendance') }, { id: 'routine', label: MA.t('nav.class_routine', 'Class routine') }];
      if (this.d.fees) t.push({ id: 'fees', label: MA.t('nav.fees', 'Fees') });
      if (this.role === 'admin') t.push({ id: 'login', label: MA.t('student.tab_login', 'Login') });
      return t;
    },
    initials() { return (this.d.name || '?').split(/\s+/).map(w => w[0]).slice(0, 2).join('').toUpperCase(); },
    sectionsOf(cid) { const c = this.classes.find(x => x.id == cid); return c ? c.sections : []; },
    availableSubjects() { const have = this.d.subjects.map(s => s.subject_id); return this.allSubjects.filter(s => s.is_active && !have.includes(s.id)); },

    async init() {
      window.addEventListener('hashchange', () => { this.pickTab(); this.loadRoutine(); });
      this.pickTab();
      await this.load();
      this.loading = false;
      await this.loadRoutine();
      if (this.staff) {
        try { [this.classes, this.allSubjects] = await Promise.all([MA.api('/api/classes'), MA.api('/api/subjects')]); }
        catch (e) { MA.toast(e.message, 'error'); }
      }
    },
    pickTab() { const h = (location.hash || '#overview').slice(1); const ok = ['overview', 'subjects', 'attendance', 'routine', 'fees'].concat(this.role === 'admin' ? ['login'] : []); this.tab = ok.includes(h) ? h : 'overview'; },
    async loadRoutine() {
      if (this.tab !== 'routine' || !this.d.id) return;
      try {
        const qs = this.role === 'student' ? '' : `?class_id=${this.d.class_id}&section_id=${this.d.section_id}`;
        this.rtSet(await MA.api('/api/routine' + qs), 'class', false);
      } catch (e) { MA.toast(e.message, 'error'); }
    },
    async load() {
      try {
        this.d = await MA.api(`/api/students/${this.id}/profile` + (this.exam_id ? '?exam_id=' + this.exam_id : ''));
        this.exam_id = this.d.exam ? this.d.exam.id : '';
        this.f = { ...this.d, apply_class_subjects: true };
        if (this.d.fees && !this.payForm.amount) this.payForm.amount = this.d.fees.monthly_fee || '';
        document.title = this.d.name + ' — Student profile';
      } catch (e) { MA.toast(e.message, 'error'); }
    },
    async run(fn, okMsg) {
      if (this.busy) return;
      this.busy = true;
      try { const r = await fn(); if (okMsg) MA.toast(typeof okMsg === 'function' ? okMsg(r) : okMsg); return r; }
      catch (e) { MA.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },
    async saveDetails() {
      const keys = ['name', 'student_id', 'admission_no', 'class_id', 'section_id', 'roll_no', 'status', 'admission_date', 'dob', 'gender',
        'guardian_name', 'guardian_relation', 'guardian_phone', 'address', 'notes', 'apply_class_subjects'];
      const body = {};
      keys.forEach(k => { body[k] = this.f[k] === undefined ? null : this.f[k]; });
      body.class_id = Number(body.class_id); body.section_id = Number(body.section_id);
      body.roll_no = body.roll_no === '' || body.roll_no === null ? null : Number(body.roll_no);
      if (await this.run(() => MA.api('/api/students/' + this.id, { method: 'PUT', body }), (r) => 'Saved' + (r.subjects_added ? `, ${r.subjects_added} new class subject(s) added` : ''))) {
        this.editing = false; await this.load();
      }
    },
    async addSubject() {
      if (await this.run(() => MA.api(`/api/students/${this.id}/subjects`, { method: 'POST', body: { subject_id: Number(this.addSubjId) } }), 'Subject added')) { this.addSubjId = ''; await this.load(); }
    },
    async applyDefaults() {
      if (await this.run(() => MA.api(`/api/students/${this.id}/subjects/apply-class-defaults`, { method: 'POST' }), (r) => r.added ? `${r.added} class subject(s) added` : 'All class subjects already assigned')) await this.load();
    },
    async removeSubject(s) {
      if (!confirm(`Remove ${s.subject} from this student?`)) return;
      if (await this.run(() => MA.api(`/api/students/${this.id}/subjects/${s.subject_id}`, { method: 'DELETE' }), 'Subject removed')) await this.load();
    },
    async saveMark(s, input) {
      const v = input.value === '' ? null : Number(input.value);
      if (v !== null && (Number.isNaN(v) || v < 0 || v > s.max)) { MA.toast(`Marks must be between 0 and ${s.max}`, 'error'); input.value = s.marks ?? ''; return; }
      if (await this.run(() => MA.api(`/api/students/${this.id}/marks`, { method: 'POST', body: { exam_id: Number(this.exam_id), subject_id: s.subject_id, marks: v } }), `${s.subject}: saved`)) await this.load();
      else input.value = s.marks ?? '';
    },
    async pay() {
      const win = window.open('', '_blank');
      const body = { ...this.payForm, student_id: this.id, amount: Number(this.payForm.amount), fee_month: this.payForm.fee_month || null, note: this.payForm.note || null };
      const r = await this.run(() => MA.api('/api/payments', { method: 'POST', body }), (x) => 'Receipt ' + x.receipt_no + ' saved');
      if (r) { if (win) win.location = '/print/receipt/' + r.id + '?autoprint=1'; this.payForm.note = ''; await this.load(); }
      else if (win) win.close();
    },
    async createLogin() {
      const r = await this.run(() => MA.api(`/api/students/${this.id}/create-login`, { method: 'POST', body: { username: this.loginForm.username || null, password: this.loginForm.password || null } }), (x) => 'Login saved for ' + x.username);
      if (r) { this.tempPassword = r.temporary_password || ''; this.tempUser = r.username; this.loginForm = { username: '', password: '' }; await this.load(); }
    },
    async enableLogin() {
      if (await this.run(() => MA.api(`/api/students/${this.id}/enable-login`, { method: 'POST' }), 'Login enabled')) await this.load();
    },
    printSlip() {
      MA.printSlips('Student login', this.d.school_name || '', MA.credRows([{ ...this.d, username: this.tempUser, password: this.tempPassword }], 'student'));
    },
    async disableLogin() {
      if (await this.run(() => MA.api(`/api/students/${this.id}/disable-login`, { method: 'POST' }), 'Login disabled')) await this.load();
    },
  };
}
window.studentProfile = studentProfile;
