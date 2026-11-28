/* Admin app mixin: Settings (1.0.5 tabbed admin panel): general, branding + logo, currencies, languages and
   translations, SMTP email (+ test), payment gateways, SMS, administrator accounts.
   Merged into adminApp() by static/js/app.js; methods use `this` = the Alpine component.
   Secrets (passwords, API keys) are write-only: the API returns "" + "<field>_set"; empty = keep. */
window.MA.mixins = window.MA.mixins || {};
window.MA.mixins.settings = () => ({
    setTab: 'general', demoMode: false, testTo: '',
    currencyRows: [], newCurrency: { code: '', name: '', symbol: '', rate: 1, decimals: 2, is_active: true },
    languageRows: [], newLanguage: { code: '', name: '', native_name: '', is_rtl: false, is_active: true },
    tr: { lang: null, items: [], q: '', dirty: {} },
    cfg: { smtp: { security: 'starttls', port: 587 }, payments: {}, sms: { provider: 'custom' } },
    palettes: [['Emerald', '#059669', '#D97706'], ['Royal', '#4F46E5', '#F59E0B'], ['Ocean', '#0369A1', '#14B8A6'], ['Maroon', '#9F1239', '#CA8A04'], ['Slate', '#334155', '#0EA5E9']],
    gateways: [
      { id: 'stripe', label: 'Stripe', desc: 'Cards worldwide', color: 'bg-indigo-600', modes: ['test', 'live'],
        fields: [{ name: 'stripe_publishable_key', label: 'Publishable key', ph: 'pk_...' }, { name: 'stripe_secret_key', label: 'Secret key', secret: true }, { name: 'stripe_webhook_secret', label: 'Webhook signing secret', secret: true }] },
      { id: 'paypal', label: 'PayPal', desc: 'PayPal and cards', color: 'bg-sky-600', modes: ['sandbox', 'live'],
        fields: [{ name: 'paypal_client_id', label: 'Client ID' }, { name: 'paypal_client_secret', label: 'Client secret', secret: true }] },
      { id: 'sslcommerz', label: 'SSLCommerz', desc: 'Cards, mobile banking (Bangladesh)', color: 'bg-teal-600', modes: ['sandbox', 'live'],
        fields: [{ name: 'sslcommerz_store_id', label: 'Store ID' }, { name: 'sslcommerz_store_password', label: 'Store password', secret: true }] },
      { id: 'bkash', label: 'bKash', desc: 'Mobile payments (Bangladesh)', color: 'bg-pink-600', modes: ['sandbox', 'live'],
        fields: [{ name: 'bkash_app_key', label: 'App key' }, { name: 'bkash_app_secret', label: 'App secret', secret: true }, { name: 'bkash_username', label: 'Username' }, { name: 'bkash_password', label: 'Password', secret: true }] },
    ],

    async loadSettingsPage() {
      await this.loadSettings();
      await this.openSetTab(this.setTab, true);
    },
    async openSetTab(id, quiet) {
      this.setTab = id;
      this.loading = true;
      try {
        if (id === 'currencies') this.currencyRows = await MA.api('/api/currencies');
        if (id === 'languages') this.languageRows = await MA.api('/api/languages');
        if (id === 'email') this.cfg.smtp = await MA.api('/api/config/smtp');
        if (id === 'payments') this.cfg.payments = await MA.api('/api/config/payments');
        if (id === 'sms') this.cfg.sms = await MA.api('/api/config/sms');
        if (id === 'admins') this.users = await MA.api('/api/users');
        const anyCfg = this.cfg.smtp.demo_mode ?? this.cfg.payments.demo_mode ?? this.cfg.sms.demo_mode;
        if (anyCfg !== undefined) this.demoMode = !!anyCfg;
      } catch (e) { if (!quiet) MA.toast(e.message, 'error'); }
      this.loading = false;
    },

    // ---------- general + branding
    async changeLogo(e) {
      const file = e.target.files[0];
      e.target.value = '';
      if (!file) return;
      if (!/^image\/(png|jpeg|gif|webp)$/.test(file.type)) return MA.toast('Choose a PNG, JPG, GIF or WebP image', 'error');
      if (file.size > 300 * 1024) return MA.toast('Logo is too large (max 300 KB)', 'error');
      const data = await new Promise((ok, bad) => { const rd = new FileReader(); rd.onload = () => ok(rd.result); rd.onerror = bad; rd.readAsDataURL(file); });
      const r = await this.run(() => MA.api('/api/settings', { method: 'POST', body: { logo: data } }), MA.t('set.logo_saved', 'Logo saved'));
      if (r) { this.school.logo = data; setTimeout(() => location.reload(), 700); }
    },
    async removeLogo() {
      if (!confirm('Remove the school logo? The default icon is shown instead.')) return;
      const r = await this.run(() => MA.api('/api/settings', { method: 'POST', body: { logo: '' } }), MA.t('set.logo_removed', 'Logo removed'));
      if (r) { this.school.logo = ''; setTimeout(() => location.reload(), 700); }
    },
    async saveSettings() {
      if (!this.school.working_days.length) return MA.toast('Choose at least one working day', 'error');
      const s = this.school;
      const body = { address: s.address, phone: s.phone, grading_scale: s.grading_scale, working_days: s.working_days };
      await this.run(() => MA.api('/api/settings', { method: 'POST', body }), MA.t('set.saved_ok', 'Settings saved'));
    },
    async saveBranding() {
      const s = this.school;
      const hex = /^#[0-9a-fA-F]{6}$/;
      if (!hex.test(s.primary_color) || !hex.test(s.secondary_color)) return MA.toast('Colours must look like #1A2B3C', 'error');
      const body = { name: s.name, tagline: s.tagline, primary_color: s.primary_color, secondary_color: s.secondary_color, landing_enabled: !!s.landing_enabled };
      const r = await this.run(() => MA.api('/api/settings', { method: 'POST', body }), MA.t('set.branding_saved', 'Branding saved'));
      if (r) setTimeout(() => location.reload(), 900); // new colours and name everywhere
    },

    // ---------- currencies
    async addCurrency() {
      const r = await this.run(() => MA.api('/api/currencies', { method: 'POST', body: this.newCurrency }), MA.t('set.currency_added', 'Currency added'));
      if (r) { this.newCurrency = { code: '', name: '', symbol: '', rate: 1, decimals: 2, is_active: true }; this.currencyRows = await MA.api('/api/currencies'); }
    },
    async saveCurrency(c) {
      const body = { code: c.code, name: c.name, symbol: c.symbol, rate: Number(c.rate), decimals: Number(c.decimals), is_active: !!c.is_active };
      if (await this.run(() => MA.api('/api/currencies/' + c.id, { method: 'PUT', body }), MA.t('set.currency_saved', 'Currency saved'))) this.currencyRows = await MA.api('/api/currencies');
    },
    async defaultCurrency(c) {
      if (!confirm(`Make ${c.code} the default currency? Fees, receipts and reports will show ${c.symbol}. Amounts are not converted.`)) return;
      if (await this.run(() => MA.api('/api/currencies/' + c.id + '/default', { method: 'POST' }), MA.t('set.currency_default', 'Default currency changed'))) {
        try { localStorage.removeItem('ma.currency'); } catch (e) { /* ignore */ }
        setTimeout(() => location.reload(), 800);
      }
    },
    async deleteCurrency(c) {
      if (!confirm(`Delete ${c.code}?`)) return;
      if (await this.run(() => MA.api('/api/currencies/' + c.id, { method: 'DELETE' }), MA.t('set.deleted', 'Deleted'))) this.currencyRows = await MA.api('/api/currencies');
    },

    // ---------- languages + translations
    async addLanguage() {
      const r = await this.run(() => MA.api('/api/languages', { method: 'POST', body: this.newLanguage }), MA.t('set.language_added', 'Language added'));
      if (r) { this.newLanguage = { code: '', name: '', native_name: '', is_rtl: false, is_active: true }; this.languageRows = await MA.api('/api/languages'); this.openTranslations(r); }
    },
    async toggleLanguage(l) {
      const body = { code: l.code, name: l.name, native_name: l.native_name, is_rtl: l.is_rtl, is_active: !l.is_active };
      if (await this.run(() => MA.api('/api/languages/' + l.id, { method: 'PUT', body }), MA.t('set.saved_ok', 'Settings saved'))) this.languageRows = await MA.api('/api/languages');
    },
    async defaultLanguage(l) {
      if (await this.run(() => MA.api('/api/languages/' + l.id + '/default', { method: 'POST' }), MA.t('set.language_default', 'Default language changed'))) this.languageRows = await MA.api('/api/languages');
    },
    async deleteLanguage(l) {
      if (!confirm(`Delete ${l.name} and its translations?`)) return;
      if (await this.run(() => MA.api('/api/languages/' + l.id, { method: 'DELETE' }), MA.t('set.deleted', 'Deleted'))) { this.languageRows = await MA.api('/api/languages'); if (this.tr.lang && this.tr.lang.id === l.id) this.tr.lang = null; }
    },
    async openTranslations(l) {
      this.loading = true;
      try { const r = await MA.api('/api/languages/' + l.id + '/translations'); this.tr = { lang: r.language, items: r.items, q: '', dirty: {} }; }
      catch (e) { MA.toast(e.message, 'error'); }
      this.loading = false;
      this.$nextTick(() => { const el = document.querySelector('[data-translation-editor]'); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); });
    },
    trItems() {
      const q = (this.tr.q || '').toLowerCase();
      const items = q ? this.tr.items.filter(i => (i.key + ' ' + i.english + ' ' + i.custom + ' ' + i.builtin).toLowerCase().includes(q)) : this.tr.items;
      return items.slice(0, 400);
    },
    async saveTranslations() {
      const items = { ...this.tr.dirty };
      const r = await this.run(() => MA.api('/api/languages/' + this.tr.lang.id + '/translations', { method: 'PUT', body: { items } }), (x) => `${x.changed} ` + MA.t('set.translations_saved', 'translation(s) saved'));
      if (r) this.tr.dirty = {};
    },

    // ---------- SMTP / payments / SMS
    async saveConfig(section) {
      const body = { ...this.cfg[section] };
      Object.keys(body).forEach((k) => { if (k.endsWith('_set') || k.endsWith('_mask') || k === 'demo_mode') delete body[k]; });
      const r = await this.run(() => MA.api('/api/config/' + section, { method: 'PUT', body }));
      if (!r) return;
      if (r.skipped_secrets && r.skipped_secrets.length) MA.toast(MA.t('set.demo_secrets_skipped', 'Saved. Demo mode: passwords and API keys were not stored.'), 'warn');
      else MA.toast(MA.t('set.saved_ok', 'Settings saved'));
      this.cfg[section] = await MA.api('/api/config/' + section);
    },
    async testEmail() {
      await this.run(() => MA.api('/api/config/smtp/test', { method: 'POST', body: { to: this.testTo } }), MA.t('set.test_sent', 'Test email sent. Check the inbox.'));
    },

    // ---------- administrators
    async createUser() {
      if (await this.run(() => MA.api('/api/users', { method: 'POST', body: { ...this.newUser, role: 'admin' } }), 'Administrator account created')) {
        this.newUser = { username: '', full_name: '', role: 'admin', password: '' };
        this.users = await MA.api('/api/users');
      }
    },
    async resetUserPassword(u) {
      const pw = prompt(`New temporary password for ${u.username} (min 8 characters):`);
      if (!pw) return;
      const body = u.has_password ? { password: pw } : { password: pw, is_active: true };
      if (await this.run(() => MA.api('/api/users/' + u.id, { method: 'PUT', body }), u.has_password ? 'Password reset' : 'Password set and account enabled')) this.users = await MA.api('/api/users');
    },
    async toggleUser(u) {
      if (!u.is_active && !u.has_password) return MA.toast('Set a password first (Set password) — the account is enabled with it.', 'warn');
      if (await this.run(() => MA.api('/api/users/' + u.id, { method: 'PUT', body: { is_active: !u.is_active } }), u.is_active ? 'Account disabled' : 'Account enabled')) this.users = await MA.api('/api/users');
    },
});
