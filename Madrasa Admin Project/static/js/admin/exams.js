/* Admin app mixin: Exams, marks entry grid and results.
   Merged into adminApp() by static/js/app.js; methods use `this` = the Alpine component. */
window.MA.mixins = window.MA.mixins || {};
window.MA.mixins.exams = () => ({
    // ---------- exams, marks, results
    currentExam() { return this.exams.find(e => e.id == this.ex.exam_id); },
    async loadExams() {
      await this.loadClasses();
      this.exams = await MA.api('/api/exams');
      if (!this.currentExam() && this.exams[0]) this.ex.exam_id = this.exams[0].id;
      if (!this.ex.class_id && this.classes[0]) this.ex.class_id = (this.classes.find(c => c.student_count) || this.classes[0]).id;
      await this.loadExamView();
    },
    async loadExamView() {
      if (!this.ex.exam_id || !this.ex.class_id) { this.sheet = { subjects: [], students: [], editable_subject_ids: [] }; this.results = []; return; }
      if (Object.keys(this.dirty).length && !confirm('Discard unsaved marks?')) return;
      this.dirty = {};
      try {
        const qs = new URLSearchParams({ exam_id: this.ex.exam_id, class_id: this.ex.class_id, section_id: this.ex.section_id || 0 });
        if (this.ex.tab === 'marks') {
          this.sheet = await MA.api('/api/marks?' + qs);
          if (!this.sheet.editable_subject_ids) this.sheet.editable_subject_ids = this.sheet.subjects.map(x => x.id);
          if (!this.sheet.subjects.some(x => x.id == this.ex.subject_id)) {
            const first = this.sheet.subjects.find(x => this.canEdit(x)) || this.sheet.subjects[0];
            this.ex.subject_id = first ? first.id : '';
          }
        }
        else this.results = (await MA.api('/api/results?' + qs)).results;
      } catch (e) { MA.toast(e.message, 'error'); }
    },
    canEdit(sub) { return this.role === 'admin' || (this.sheet.editable_subject_ids || []).includes(sub.id); },
    currentSubject() { return this.sheet.subjects.find(x => x.id == this.ex.subject_id); },
    setMark(st, sub, value) {
      st.marks[sub.id] = value === '' ? null : Number(value);
      this.dirty[st.id + ':' + sub.id] = { student_id: st.id, subject_id: sub.id, marks: value === '' ? null : Number(value) };
    },
    markInvalid(st, sub) { const v = st.marks[sub.id]; return v !== null && v !== undefined && (v < 0 || v > sub.max_marks || Number.isNaN(v)); },
    async saveMarks() {
      const entries = Object.values(this.dirty);
      const bad = this.sheet.students.some(st => this.sheet.subjects.some(sub => this.markInvalid(st, sub)));
      if (bad) { MA.toast('Some marks are out of range (red boxes). Fix them first.', 'error'); return; }
      const sent = { ...this.dirty };
      const r = await this.run(() => MA.api('/api/marks/bulk', { method: 'POST', body: { exam_id: Number(this.ex.exam_id), entries } }), (x) => `${x.saved} mark(s) saved`);
      if (r) {
        // keep any edit typed while the save was running
        Object.keys(sent).forEach(k => { if (this.dirty[k] === sent[k]) delete this.dirty[k]; });
        if (!Object.keys(this.dirty).length) await this.loadExamView();
      }
    },
    async createExam() {
      if (!this.newExam.name.trim()) return MA.toast('Enter an exam name', 'error');
      const r = await this.run(() => MA.api('/api/exams', { method: 'POST', body: { ...this.newExam, exam_date: this.newExam.exam_date || null, is_published: false } }), 'Exam added (draft — publish when results are ready)');
      if (r) { this.newExam = { name: '', exam_date: '' }; this.ex.exam_id = r.id; await this.loadExams(); }
    },
    async togglePublish() {
      const e = this.currentExam();
      const r = await this.run(() => MA.api('/api/exams/' + e.id, { method: 'PUT', body: { name: e.name, exam_date: e.exam_date, is_published: !e.is_published } }), e.is_published ? 'Exam hidden from students' : 'Exam published to students');
      if (r) { this.exams = await MA.api('/api/exams'); }
    },
    async deleteExam() {
      const e = this.currentExam();
      if (!confirm(`Delete exam ${e.name}?`)) return;
      if (await this.run(() => MA.api('/api/exams/' + e.id, { method: 'DELETE' }), 'Exam deleted')) { this.ex.exam_id = ''; await this.loadExams(); }
    },
});
