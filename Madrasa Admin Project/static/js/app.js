/* Admin / teacher single-page UI (Alpine.js): a thin shell (state, routing, shared lookups).
   Each page's methods live in static/js/admin/<feature>.js as a mixin (MA.mixins.<feature>) and are
   merged below, like MA.routineMixin. Load order (templates/index.html): common.js, admin/*.js, app.js. */
function adminApp() {
  const PAGES = ['dashboard', 'students', 'teachers', 'logins', 'routine', 'subjects', 'exams', 'attendance', 'fees', 'classes', 'settings'];
  const ADMIN_ONLY = ['teachers', 'logins', 'fees', 'classes', 'settings'];

  return {
    ...MA.routineMixin(),
    ...MA.mixins.students(),
    ...MA.mixins.exams(),
    ...MA.mixins.attendance(),
    ...MA.mixins.fees(),
    ...MA.mixins.routine(),
    ...MA.mixins.classes(),
    ...MA.mixins.accounts(),
    ...MA.mixins.settings(),
    MA: window.MA,
    role: document.body.dataset.role,
    page: 'dashboard', navOpen: false, busy: false, loading: false,
    statuses: ['Active', 'Inactive', 'Transferred', 'Graduated', 'Archived'],
    methods: ['Cash', 'bKash', 'Nagad', 'Rocket', 'Bank', 'Card', 'Other'],
    school: { name: '', tagline: '', address: '', phone: '', logo: '', grading_scale: 'standard', currency: '৳', working_days: [], primary_color: '#059669', secondary_color: '#D97706', landing_enabled: true }, scales: {},
    allDays: [], dayNames: {},
    get cur() { return this.school.currency || '৳'; },
    dash: {}, classes: [], subjects: [], students: [], exams: [], results: [], payments: [], users: [],
    stuFilter: { q: '', class_id: '', section_id: '', status: 'current' },
    stuForm: { open: false, id: null, d: MA.blank.student() },
    subForm: { open: false, id: null, d: MA.blank.subject() },
    classSubj: { class_id: '', ids: [] },
    ex: { exam_id: '', class_id: '', section_id: '', tab: 'marks', view: window.innerWidth < 768 ? 'subject' : 'grid', subject_id: '' },
    sheet: { subjects: [], students: [], editable_subject_ids: [] }, dirty: {},
    newExam: { name: '', exam_date: '' },
    att: { date: MA.today(), class_id: '', section_id: '', students: [], saved: false },
    attReport: { month: MA.thisMonth(), rows: [] },
    fee: { class_id: '', q: '', student_id: '', amount: '', fee_month: MA.thisMonth(), fee_head: 'Monthly Tuition', method: 'Cash', note: '', status: null },
    feeStudents: [], dues: { class_id: '', rows: [] },
    newClassName: '', newSection: {}, newUser: { username: '', full_name: '', role: 'admin', password: '' },

    // 1.3.0: teachers page, student logins page, credentials slip
    teacherRows: [], teacherQ: '', tForm: { open: false, id: null, show: false, touched: false, d: MA.blank.teacher() },
    loginRows: [], lg: { class_id: '', section_id: '', q: '', reset_existing: false },
    cred: { open: false, title: '', rows: [], skipped: [] },

    // routine page
    rtTab: 'class', rtSel: { class_id: '', section_id: '' }, rtTeacher: '', rtMeta: { default_teachers: {}, subject_ids: [], class_name: '', section_name: '' },
    teachers: [], assignments: [], asgFilter: { class_id: '', teacher_id: '' }, newAsg: { teacher_id: '', class_id: '', section_id: '', subject_id: '' },
    periodsList: [], perForm: { id: null, name: '', start_time: '', end_time: '', is_break: false, order: 0 },
    cellForm: { open: false, day: '', period: null, slot: null, subject_id: '', teacher_id: '', room: '' },
    todayList: [],

    async init() {
      if (this.role === 'teacher') this.rtTab = 'mine';
      window.addEventListener('hashchange', () => this.route());
      window.addEventListener('beforeunload', (e) => { if (Object.keys(this.dirty).length) { e.preventDefault(); e.returnValue = ''; } });
      try {
        await Promise.all([this.loadSettings(), this.loadClasses()]);
      } catch (e) { MA.toast(e.message, 'error'); }
      await this.route();
    },
    async route() {
      let p = (location.hash || '#dashboard').slice(1);
      if (!PAGES.includes(p) || (ADMIN_ONLY.includes(p) && this.role !== 'admin')) p = 'dashboard';
      if (this.page === 'exams' && p !== 'exams' && Object.keys(this.dirty).length &&
          !confirm('You have unsaved marks. Leave without saving?')) { history.replaceState(null, '', '#exams'); return; }
      if (p !== 'exams') this.dirty = {};
      this.page = p;
      this.navOpen = false;
      await this.load();
    },
    async load() {
      this.loading = true;
      try {
        const p = this.page;
        if (p === 'dashboard') this.dash = await MA.api('/api/dashboard');
        if (p === 'routine') await this.loadRoutinePage();
        if (p === 'students') { await this.loadClasses(); await this.loadStudents(); }
        if (p === 'subjects') { await this.loadClasses(); await this.loadSubjects(); if (this.role !== 'admin') this.assignments = await MA.api('/api/assignments'); }
        if (p === 'teachers') await this.loadTeachers();
        if (p === 'logins') { await this.loadClasses(); await this.loadLogins(); }
        if (p === 'exams') await this.loadExams();
        if (p === 'attendance') { await this.loadClasses(); if (!this.att.class_id && this.classes[0]) this.att.class_id = this.classes[0].id; await this.loadAttendance(); }
        if (p === 'fees') { await this.loadClasses(); await Promise.all([this.loadFeeStudents(), this.loadPayments(), this.loadDues()]); }
        if (p === 'classes') await this.loadClasses();
        if (p === 'settings') await this.loadSettingsPage();
      } catch (e) { MA.toast(e.message, 'error'); }
      this.loading = false;
    },
    async run(fn, okMsg) {
      if (this.busy) return;
      this.busy = true;
      try { const r = await fn(); if (okMsg) MA.toast(typeof okMsg === 'function' ? okMsg(r) : okMsg); return r; }
      catch (e) { MA.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    // ---------- shared lookups
    async loadClasses() { this.classes = await MA.api('/api/classes'); },
    async loadSubjects() { this.subjects = await MA.api('/api/subjects'); },
    async loadSettings() {
      const s = await MA.api('/api/settings');
      this.scales = s.scales;
      this.school = { name: s.name, tagline: s.tagline || '', address: s.address, phone: s.phone, logo: s.logo || '', grading_scale: s.grading_scale, currency: s.currency, working_days: s.working_days || [],
        primary_color: s.primary_color, secondary_color: s.secondary_color, landing_enabled: s.landing_enabled };
      this.allDays = s.all_days || []; this.dayNames = s.day_names || {};
      if (s.payment_methods && s.payment_methods.length) this.methods = s.payment_methods;
      this.demoMode = !!s.demo_mode;
    },
    // 1.0.5: top bar title and dashboard chart helpers
    pageLabel() {
      const L = { dashboard: ['nav.dashboard', 'Dashboard'], students: this.role === 'teacher' ? ['nav.my_students', 'My students'] : ['nav.students', 'Students'],
        teachers: ['nav.teachers', 'Teachers'], logins: ['nav.logins', 'Student logins'], routine: this.role === 'teacher' ? ['nav.my_routine', 'My routine'] : ['nav.routine', 'Class routine'],
        subjects: this.role === 'teacher' ? ['nav.my_subjects', 'My subjects'] : ['nav.subjects', 'Subjects'], exams: this.role === 'teacher' ? ['nav.marks_results', 'Marks & results'] : ['nav.exams', 'Exams & Results'],
        attendance: ['nav.attendance', 'Attendance'], fees: ['nav.fees', 'Fees'], classes: ['nav.classes', 'Classes'], settings: ['nav.settings', 'Settings'] }[this.page] || ['nav.dashboard', 'Dashboard'];
      return MA.t(L[0], L[1]);
    },
    attRate() {
      const a = this.dash.attendance_today || {};
      const total = (a.Present || 0) + (a.Late || 0) + (a.Absent || 0) + (a.Leave || 0);
      return total ? Math.round(100 * ((a.Present || 0) + (a.Late || 0)) / total) : null;
    },
    donut(status) {
      const a = this.dash.attendance_today || {};
      const total = (a.Present || 0) + (a.Late || 0) + (a.Absent || 0) + (a.Leave || 0);
      return total ? Math.round(1000 * (a[status] || 0) / total) / 10 : 0;
    },
    barPct(v, all) { const max = Math.max(...(all || [0]), 0); return max ? Math.round(100 * (Number(v) || 0) / max) : 0; },
    sectionsOf(classId) { const c = this.classes.find(x => x.id == classId); return c ? c.sections : []; },
    className(id) { const c = this.classes.find(x => x.id == id); return c ? c.name : '#' + id; },

  };
}
window.adminApp = adminApp;
