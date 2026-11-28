/* Admin app mixin: Fee collection, receipts and dues (admin).
   Merged into adminApp() by static/js/app.js; methods use `this` = the Alpine component. */
window.MA.mixins = window.MA.mixins || {};
window.MA.mixins.fees = () => ({
    // ---------- fees
    async loadFeeStudents() {
      const qs = new URLSearchParams({ q: this.fee.q, class_id: this.fee.class_id || 0, status: 'current' });
      this.feeStudents = await MA.api('/api/students?' + qs);
    },
    async loadPayments() { this.payments = await MA.api('/api/payments'); },
    async loadDues() { this.dues.rows = await MA.api('/api/fees/dues?class_id=' + (this.dues.class_id || 0)); },
    async pickFeeStudent() {
      this.fee.status = null;
      if (!this.fee.student_id) return;
      try {
        const p = await MA.api(`/api/students/${this.fee.student_id}/profile`);
        this.fee.status = p.fees;
        this.fee.amount = p.fees.monthly_fee || this.fee.amount;
      } catch (e) { MA.toast(e.message, 'error'); }
    },
    async pay() {
      const body = { student_id: Number(this.fee.student_id), amount: Number(this.fee.amount), method: this.fee.method, fee_month: this.fee.fee_month || null, fee_head: this.fee.fee_head || 'Monthly Tuition', note: this.fee.note || null };
      const win = window.open('', '_blank');
      const r = await this.run(() => MA.api('/api/payments', { method: 'POST', body }), (x) => 'Receipt ' + x.receipt_no + ' saved');
      if (r) {
        if (win) win.location = '/print/receipt/' + r.id + '?autoprint=1';
        this.fee.note = '';
        await Promise.all([this.loadPayments(), this.loadDues(), this.pickFeeStudent()]);
      } else if (win) win.close();
    },
    async voidPayment(p) {
      if (!confirm(`Void receipt ${p.receipt_no}? It stays in the list but no longer counts as paid.`)) return;
      if (await this.run(() => MA.api(`/api/payments/${p.id}/void`, { method: 'POST' }), 'Receipt voided')) await Promise.all([this.loadPayments(), this.loadDues()]);
    },
    async setFeePlan(c, value) {
      const amount = Number(value);
      if (Number.isNaN(amount) || amount < 0) return MA.toast('Enter a valid amount', 'error');
      if (await this.run(() => MA.api('/api/fees/plans', { method: 'PUT', body: { class_id: c.id, amount } }), `${c.name}: monthly fee ${MA.money(amount, this.cur)}`)) { c.monthly_fee = amount; await this.loadDues(); }
    },
});
