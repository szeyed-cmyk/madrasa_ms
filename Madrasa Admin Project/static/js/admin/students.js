/* Admin app mixin: Students list/form/import/export and subjects (admin; teachers see their classes).
   Merged into adminApp() by static/js/app.js; methods use `this` = the Alpine component. */
window.MA.mixins = window.MA.mixins || {};
window.MA.mixins.students = () => ({
    // ---------- students
    async loadStudents() {
      const f = this.stuFilter;
      const qs = new URLSearchParams({ q: f.q, class_id: f.class_id || 0, section_id: f.section_id || 0, status: f.status });
      this.students = await MA.api('/api/students?' + qs);
    },
    openStudentForm(s) {
      if (s) {
        const d = MA.blank.student();
        Object.keys(d).forEach(k => { if (s[k] !== undefined && s[k] !== null) d[k] = s[k]; });
        d.apply_class_subjects = true;
        this.stuForm = { open: true, id: s.id, d };
      } else {
        const d = MA.blank.student();
        if (this.stuFilter.class_id) { d.class_id = this.stuFilter.class_id; d.section_id = (this.sectionsOf(d.class_id)[0] || {}).id || ''; }
        this.stuForm = { open: true, id: null, d };
      }
    },
    pickPhoto(e, target) {
      const file = e.target.files[0];
      e.target.value = '';
      if (!file) return;
      if (file.size > 300 * 1024) { MA.toast('Photo is too large (max 300 KB).', 'warn'); return; }
      const reader = new FileReader();
      reader.onload = () => { target.photo = reader.result; };
      reader.readAsDataURL(file);
    },
    async saveStudent() {
      const d = { ...this.stuForm.d, class_id: Number(this.stuForm.d.class_id), section_id: Number(this.stuForm.d.section_id) };
      d.roll_no = d.roll_no === '' || d.roll_no === null ? null : Number(d.roll_no);
      const id = this.stuForm.id;
      const r = await this.run(() => MA.api(id ? '/api/students/' + id : '/api/students', { method: id ? 'PUT' : 'POST', body: d }),
        (res) => id ? 'Student updated' : `Student added (ID ${res.student_id}, ${res.subjects_added} subjects assigned)`);
      if (r) { this.stuForm.open = false; await this.loadStudents(); }
    },
    async changeStatus(s, status) {
      const r = await this.run(() => MA.api(`/api/students/${s.id}/status`, { method: 'POST', body: { status } }), `${s.name}: ${status}`);
      if (r) s.status = status; else await this.loadStudents();
    },
    async deleteStudent(s) {
      if (!confirm(`Delete ${s.name} permanently? Marks, attendance and subjects of this student are deleted too. (Students with payments can only be archived.)`)) return;
      if (await this.run(() => MA.api('/api/students/' + s.id, { method: 'DELETE' }), 'Student deleted')) await this.loadStudents();
    },
    async importCsv(e) {
      const file = e.target.files[0];
      e.target.value = '';
      if (!file) return;
      const fd = new FormData(); fd.append('file', file);
      const r = await this.run(() => MA.api('/api/students/import', { method: 'POST', body: fd }));
      if (r) {
        MA.toast(`Imported ${r.created} student(s)` + (r.errors.length ? `, ${r.errors.length} row(s) skipped` : ''), r.errors.length ? 'warn' : 'ok');
        if (r.errors.length) alert('Rows not imported:\n\n' + r.errors.slice(0, 40).join('\n'));
        await this.loadStudents();
      }
    },

    // ---------- subjects
    openSubjectForm(s) {
      this.subForm = s ? { open: true, id: s.id, d: { name: s.name, code: s.code || '', max_marks: s.max_marks, pass_marks: s.pass_marks, credits: s.credits, is_active: s.is_active, class_ids: [...s.class_ids] } }
        : { open: true, id: null, d: MA.blank.subject() };
    },
    async saveSubject() {
      const id = this.subForm.id;
      const d = { ...this.subForm.d, pass_marks: this.subForm.d.pass_marks === '' ? null : this.subForm.d.pass_marks };
      const r = await this.run(() => MA.api(id ? '/api/subjects/' + id : '/api/subjects', { method: id ? 'PUT' : 'POST', body: d }), id ? 'Subject updated' : 'Subject added');
      if (r) { this.subForm.open = false; await Promise.all([this.loadSubjects(), this.loadClasses()]); this.pickClassSubjects(); }
    },
    async deleteSubject(s) {
      if (!confirm(`Delete subject ${s.name}? It is removed from all classes and students.`)) return;
      if (await this.run(() => MA.api('/api/subjects/' + s.id, { method: 'DELETE' }), 'Subject deleted')) { await Promise.all([this.loadSubjects(), this.loadClasses()]); this.pickClassSubjects(); }
    },
    pickClassSubjects() { const c = this.classes.find(x => x.id == this.classSubj.class_id); this.classSubj.ids = c ? [...c.subject_ids] : []; },
    toggleClassSubject(id, on) { this.classSubj.ids = on ? [...new Set([...this.classSubj.ids, id])] : this.classSubj.ids.filter(x => x !== id); },
    async saveClassSubjects() {
      const r = await this.run(() => MA.api(`/api/classes/${this.classSubj.class_id}/subjects`, { method: 'PUT', body: { subject_ids: this.classSubj.ids } }), 'Class default subjects saved');
      if (r) await Promise.all([this.loadSubjects(), this.loadClasses()]);
    },
    async applyClassSubjects() {
      if (!confirm('Add this class\'s default subjects to every current student in the class? Existing subjects and marks are kept.')) return;
      await this.saveClassSubjects();
      await this.run(() => MA.api(`/api/classes/${this.classSubj.class_id}/subjects/apply`, { method: 'POST' }),
        (r) => `${r.assignments_added} subject assignment(s) added for ${r.students} student(s)`);
      await this.loadSubjects();
    },
});
