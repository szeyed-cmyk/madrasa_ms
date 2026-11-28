/* Admin app mixin: Routine page: class/teacher timetable, teacher assignments, periods.
   Merged into adminApp() by static/js/app.js; methods use `this` = the Alpine component. */
window.MA.mixins = window.MA.mixins || {};
window.MA.mixins.routine = () => ({
    // ---------- routine, teacher assignments, periods
    async loadRoutinePage() {
      await this.loadClasses();
      if (!this.subjects.length) await this.loadSubjects();
      if (!this.teachers.length) this.teachers = await MA.api('/api/teachers');
      if (!this.rtSel.class_id && this.classes[0]) {
        const c = this.classes.find(x => x.student_count) || this.classes[0];
        this.rtSel.class_id = c.id; this.rtSel.section_id = (c.sections[0] || {}).id || '';
      }
      if (this.role !== 'admin' && !['class', 'mine'].includes(this.rtTab)) this.rtTab = 'mine';
      await this.loadRtTab();
    },
    async loadRtTab() {
      try {
        if (this.rtTab === 'class') await this.loadClassRoutine();
        if (this.rtTab === 'mine') await this.loadTeacherRoutine();
        if (this.rtTab === 'assign') await this.loadAssignments();
        if (this.rtTab === 'periods') this.periodsList = await MA.api('/api/periods');
      } catch (e) { MA.toast(e.message, 'error'); }
    },
    rtPickClass() { this.rtSel.section_id = (this.sectionsOf(this.rtSel.class_id)[0] || {}).id || ''; this.loadClassRoutine(); },
    async loadClassRoutine() {
      if (!this.rtSel.section_id) { this.rtSet({}, 'class', false); return; }
      const d = await MA.api(`/api/routine?class_id=${this.rtSel.class_id || 0}&section_id=${this.rtSel.section_id}`);
      this.rtMeta = { default_teachers: d.default_teachers || {}, subject_ids: d.subject_ids || [], class_name: d.class_name, section_name: d.section_name };
      this.rtSet(d, 'class', this.role === 'admin');
    },
    async loadTeacherRoutine() {
      const q = (this.role === 'admin' && this.rtTeacher) ? '?teacher_id=' + this.rtTeacher : '';
      const d = await MA.api('/api/my/routine' + q);
      this.rtTeacher = this.role === 'admin' ? d.teacher_id : '';
      this.rtMeta.teacher_name = d.teacher_name; this.rtMeta.teacher_id = d.teacher_id;
      this.todayList = d.today_classes || [];
      this.rtSet(d, 'teacher', false);
    },
    teacherOf(id) { const t = this.teachers.find(x => x.id == id); return t ? t.name : ''; },
    subjectName(id) { const s = this.subjects.find(x => x.id == id); return s ? s.name : '#' + id; },
    cellSubjects() {
      const ids = this.rtMeta.subject_ids || [];
      const list = this.subjects.filter(s => ids.includes(s.id));
      return list.length ? list : this.subjects;
    },
    rtClick(day, period) {
      if (!this.rtEditable || period.is_break) return;
      const slot = this.rtCell(day, period.id);
      this.cellForm = { open: true, day, period, slot, subject_id: slot ? slot.subject_id : '', teacher_id: slot ? (slot.teacher_id || '') : '', room: slot ? slot.room : '' };
    },
    cellPickSubject() {
      const t = this.rtMeta.default_teachers[String(this.cellForm.subject_id)];
      this.cellForm.teacher_id = t || '';
    },
    cellAssigned() {
      const sid = String(this.cellForm.subject_id);
      if (!sid || !this.cellForm.teacher_id) return true;
      return this.rtMeta.default_teachers[sid] == this.cellForm.teacher_id;
    },
    async saveCell() {
      const f = this.cellForm;
      if (!f.subject_id) return MA.toast('Choose a subject', 'error');
      const body = { class_id: Number(this.rtSel.class_id), section_id: Number(this.rtSel.section_id), day: f.day, period_id: f.period.id,
        subject_id: Number(f.subject_id), teacher_id: f.teacher_id ? Number(f.teacher_id) : null, room: f.room || '' };
      const r = await this.run(() => MA.api('/api/routine/slot', { method: 'PUT', body }), 'Routine updated');
      if (r) { this.cellForm.open = false; await this.loadClassRoutine(); }
    },
    async clearCell() {
      const f = this.cellForm;
      if (!f.slot) { f.open = false; return; }
      const r = await this.run(() => MA.api('/api/routine/slot/' + f.slot.id, { method: 'DELETE' }), 'Period cleared');
      if (r) { this.cellForm.open = false; await this.loadClassRoutine(); }
    },
    printClassRoutine() { if (this.rtSel.section_id) window.open('/print/routine?section_id=' + this.rtSel.section_id, '_blank'); },
    printTeacherRoutine() { if (this.rtMeta.teacher_id) window.open('/print/routine/teacher/' + this.rtMeta.teacher_id, '_blank'); },
    async loadAssignments() {
      const qs = new URLSearchParams({ class_id: this.asgFilter.class_id || 0, teacher_id: this.asgFilter.teacher_id || 0 });
      this.assignments = await MA.api('/api/assignments?' + qs);
    },
    async saveAssignment() {
      const a = this.newAsg;
      if (!a.teacher_id || !a.class_id || !a.subject_id) return MA.toast('Choose a teacher, class and subject', 'error');
      const body = { teacher_id: Number(a.teacher_id), class_id: Number(a.class_id), section_id: a.section_id ? Number(a.section_id) : null, subject_id: Number(a.subject_id) };
      const r = await this.run(() => MA.api('/api/assignments', { method: 'POST', body }), (x) => x.replaced ? 'Teacher assigned (replaces ' + x.replaced + ')' : 'Teacher assigned');
      if (r) { this.newAsg.subject_id = ''; await this.loadAssignments(); }
    },
    async deleteAssignment(a) {
      if (!confirm(`Remove ${a.teacher_name} from ${a.subject_name} (${a.class_name}${a.section_name ? ' - ' + a.section_name : ''})?`)) return;
      if (await this.run(() => MA.api('/api/assignments/' + a.id, { method: 'DELETE' }), 'Assignment removed')) await this.loadAssignments();
    },
    editPeriod(p) { this.perForm = p ? { ...p } : { id: null, name: '', start_time: '', end_time: '', is_break: false, order: (this.periodsList.length + 1) }; },
    async savePeriod() {
      const f = this.perForm;
      const body = { name: f.name, start_time: f.start_time, end_time: f.end_time, is_break: !!f.is_break, order: Number(f.order) || 0 };
      const r = await this.run(() => f.id ? MA.api('/api/periods/' + f.id, { method: 'PUT', body }) : MA.api('/api/periods', { method: 'POST', body }), f.id ? 'Period updated' : 'Period added');
      if (r) { this.editPeriod(null); this.periodsList = await MA.api('/api/periods'); }
    },
    async deletePeriod(p) {
      if (!confirm(`Delete ${p.name}? Classes placed in this period are removed from the routine.`)) return;
      const r = await this.run(() => MA.api('/api/periods/' + p.id, { method: 'DELETE' }), (x) => 'Period deleted' + (x.slots_removed ? ` (${x.slots_removed} routine entries removed)` : ''));
      if (r) this.periodsList = await MA.api('/api/periods');
    },
    toggleDay(d, on) {
      const set = new Set(this.school.working_days);
      on ? set.add(d) : set.delete(d);
      this.school.working_days = this.allDays.filter(x => set.has(x));
    },
});
