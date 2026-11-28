/* Admin app mixin: Daily attendance and monthly report.
   Merged into adminApp() by static/js/app.js; methods use `this` = the Alpine component. */
window.MA.mixins = window.MA.mixins || {};
window.MA.mixins.attendance = () => ({
    // ---------- attendance
    async loadAttendance() {
      if (!this.att.class_id) return;
      const qs = new URLSearchParams({ date: this.att.date, class_id: this.att.class_id, section_id: this.att.section_id || 0 });
      const r = await MA.api('/api/attendance?' + qs);
      this.att.students = r.students.map(s => ({ ...s, status: s.status || 'Present' }));
      this.att.saved = r.already_saved;
    },
    async saveAttendance() {
      const records = this.att.students.map(s => ({ student_id: s.id, status: s.status }));
      const r = await this.run(() => MA.api('/api/attendance', { method: 'POST', body: { date: this.att.date, records } }), (x) => `Attendance saved for ${x.saved} student(s)`);
      if (r) this.att.saved = true;
    },
    async loadAttReport() {
      try { this.attReport.rows = (await MA.api(`/api/attendance/report?month=${this.attReport.month}&class_id=${this.att.class_id || 0}`)).rows; if (!this.attReport.rows.length) MA.toast('No students', 'warn'); }
      catch (e) { MA.toast(e.message, 'error'); }
    },
});
