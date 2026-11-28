/* Admin app mixin: Classes and sections (admin).
   Merged into adminApp() by static/js/app.js; methods use `this` = the Alpine component. */
window.MA.mixins = window.MA.mixins || {};
window.MA.mixins.classes = () => ({
    // ---------- classes
    async addClass() {
      if (!this.newClassName.trim()) return;
      if (await this.run(() => MA.api('/api/classes', { method: 'POST', body: { name: this.newClassName } }), 'Class added with Section A')) { this.newClassName = ''; await this.loadClasses(); }
    },
    async renameClass(c) {
      const name = prompt('New name for ' + c.name, c.name);
      if (!name || name.trim() === c.name) return;
      if (await this.run(() => MA.api('/api/classes/' + c.id, { method: 'PUT', body: { name } }), 'Class renamed')) await this.loadClasses();
    },
    async deleteClass(c) {
      if (!confirm(`Delete ${c.name}? Its sections, default subjects and fee plan are removed too.`)) return;
      if (await this.run(() => MA.api('/api/classes/' + c.id, { method: 'DELETE' }), 'Class deleted')) await this.loadClasses();
    },
    async addSection(c) {
      const name = (this.newSection[c.id] || '').trim();
      if (!name) return;
      if (await this.run(() => MA.api('/api/sections', { method: 'POST', body: { class_id: c.id, name } }), 'Section added')) { this.newSection[c.id] = ''; await this.loadClasses(); }
    },
    async deleteSection(sec) {
      if (!confirm('Delete section ' + sec.name + '?')) return;
      if (await this.run(() => MA.api('/api/sections/' + sec.id, { method: 'DELETE' }), 'Section deleted')) await this.loadClasses();
    },
});
