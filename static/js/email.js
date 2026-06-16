/* eslint-disable */
// Email module — Instantly-style cold email UI
// Exposes window.EmailModule and window.switchEmailTab

(function () {
  'use strict';

  const state = {
    accounts: [],
    campaigns: [],
    activeTab: 'overview',
    inboxReplies: [],
    builder: null, // current campaign being edited
  };

  // ============ Utility helpers ============
  async function api(path, opts = {}) {
    const resp = await fetch(path, {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      ...opts,
    });
    return resp.json();
  }

  function toast(msg, kind = 'info') {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.className = `toast toast-${kind} show`;
    setTimeout(() => t.classList.remove('show'), 3500);
  }

  function el(html) {
    const div = document.createElement('div');
    div.innerHTML = html.trim();
    return div.firstChild;
  }

  function escapeHtml(str) {
    if (str == null) return '';
    return String(str).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  // ============ Tab switching ============
  function switchEmailTab(tab) {
    state.activeTab = tab;
    document.querySelectorAll('.email-tab').forEach(b => {
      b.classList.toggle('active', b.dataset.emailTab === tab);
    });
    document.querySelectorAll('.email-pane').forEach(p => p.classList.remove('active'));
    const pane = document.getElementById(`email-pane-${tab}`);
    if (pane) pane.classList.add('active');

    if (tab === 'overview') loadOverview();
    if (tab === 'campaigns') loadCampaignsList();
    if (tab === 'inbox') loadInbox();
    if (tab === 'accounts') loadAccounts();
  }
  window.switchEmailTab = switchEmailTab;

  // ============ Overview ============
  async function loadOverview() {
    const data = await api('/api/email/stats');
    if (!data.success) return;
    const s = data.stats || {};
    document.getElementById('email-stat-sent').textContent = s.total_sends || 0;
    document.getElementById('email-stat-opens').textContent = (s.open_rate || 0) + '%';
    document.getElementById('email-stat-replies').textContent = (s.reply_rate || 0) + '%';
    document.getElementById('email-stat-clicks').textContent = (s.click_rate || 0) + '%';

    // Account summary
    const accountWrap = document.getElementById('email-account-summary');
    if (!data.accounts || data.accounts.length === 0) {
      accountWrap.innerHTML = '<p class="muted">No mailboxes connected yet. <a href="#" onclick="switchEmailTab(\'accounts\'); return false">Connect one</a> to start sending.</p>';
    } else {
      accountWrap.innerHTML = data.accounts.map(a => `
        <div class="account-summary-row">
          <span class="account-email">${escapeHtml(a.email)}</span>
          <span class="account-status status-${a.status}">${a.status}</span>
          <span class="muted">${a.sends_today || 0} / ${a.daily_cap} today</span>
        </div>
      `).join('');
    }

    // Unread badge
    const badge = document.getElementById('email-unread-badge');
    const tabBadge = document.getElementById('email-inbox-badge');
    if (s.unread_replies > 0) {
      badge.style.display = 'inline-block';
      badge.textContent = s.unread_replies;
      tabBadge.style.display = 'inline-block';
      tabBadge.textContent = s.unread_replies;
    } else {
      badge.style.display = 'none';
      tabBadge.style.display = 'none';
    }

    // Active campaigns
    const ac = await api('/api/email/campaigns?status=active');
    const acWrap = document.getElementById('email-active-campaigns');
    if (!ac.campaigns || ac.campaigns.length === 0) {
      acWrap.innerHTML = '<p class="muted">No active campaigns.</p>';
    } else {
      acWrap.innerHTML = ac.campaigns.map(c => `
        <div class="active-campaign-row">
          <div>
            <strong>${escapeHtml(c.name)}</strong>
            <div class="muted">${c.stats.sent || 0} sent · ${c.stats.reply_rate || 0}% reply · ${c.stats.bounce_rate || 0}% bounce</div>
          </div>
          <button class="btn btn-sm btn-secondary" onclick="EmailModule.openCampaign(${c.id})">View</button>
        </div>
      `).join('');
    }
  }

  // ============ Accounts ============
  async function loadAccounts() {
    const data = await api('/api/email/accounts');
    state.accounts = data.accounts || [];
    const list = document.getElementById('email-accounts-list');
    if (state.accounts.length === 0) {
      list.innerHTML = '<div class="empty-state"><i class="fas fa-server fa-3x muted"></i><p>No mailboxes connected. Connect a Gmail or Google Workspace account to start sending.</p></div>';
      return;
    }
    list.innerHTML = state.accounts.map(a => `
      <div class="account-card" data-id="${a.id}">
        <div class="account-card-header">
          <div>
            <div class="account-email-large"><i class="fab fa-google"></i> ${escapeHtml(a.email)}</div>
            <div class="muted">${escapeHtml(a.display_name || '')}</div>
          </div>
          <span class="status-pill status-${a.status}">${a.status}</span>
        </div>
        <div class="account-card-body">
          <div class="account-stat"><span class="muted">Sends today</span><strong>${a.sends_today} / ${a.daily_cap}</strong></div>
          <div class="account-stat"><span class="muted">Bounces (7d)</span><strong>${a.bounce_count_7d || 0}</strong></div>
          <div class="account-stat"><span class="muted">Last send</span><strong>${fmtDate(a.last_send_at)}</strong></div>
        </div>
        <div class="account-card-settings">
          <label>Daily cap: <input type="number" min="1" max="500" value="${a.daily_cap}" data-field="daily_cap"></label>
          <label>Jitter min (s): <input type="number" min="1" value="${a.min_delay_seconds}" data-field="min_delay_seconds"></label>
          <label>Jitter max (s): <input type="number" min="1" value="${a.max_delay_seconds}" data-field="max_delay_seconds"></label>
          <button class="btn btn-sm btn-secondary" onclick="EmailModule.saveAccount(${a.id})">Save</button>
          <button class="btn btn-sm btn-danger" onclick="EmailModule.deleteAccount(${a.id})">Disconnect</button>
        </div>
        ${a.last_error ? `<div class="account-error">${escapeHtml(a.last_error)}</div>` : ''}
      </div>
    `).join('');
  }

  async function connectAccount() {
    const data = await api('/api/email/oauth/start');
    if (!data.success) {
      toast(data.error || 'OAuth not configured (GOOGLE_CLIENT_ID missing)', 'error');
      return;
    }
    const w = window.open(data.url, 'gmail-connect', 'width=520,height=720');
    if (!w) {
      toast('Popup blocked — please allow popups for this site', 'error');
      return;
    }
    // Poll for window close, then refresh accounts
    const interval = setInterval(() => {
      if (w.closed) {
        clearInterval(interval);
        setTimeout(loadAccounts, 500);
      }
    }, 800);
  }

  async function saveAccount(id) {
    const card = document.querySelector(`.account-card[data-id="${id}"]`);
    const data = {};
    card.querySelectorAll('input[data-field]').forEach(input => {
      data[input.dataset.field] = parseInt(input.value, 10) || 0;
    });
    const r = await api(`/api/email/accounts/${id}`, { method: 'PUT', body: JSON.stringify(data) });
    if (r.success) toast('Saved', 'success');
    else toast(r.error || 'Failed', 'error');
  }

  async function deleteAccount(id) {
    if (!confirm('Disconnect this mailbox? Active campaigns using it will lose this sender.')) return;
    const r = await api(`/api/email/accounts/${id}`, { method: 'DELETE' });
    if (r.success) {
      toast('Disconnected', 'success');
      loadAccounts();
    }
  }

  // ============ Campaigns list ============
  async function loadCampaignsList() {
    const data = await api('/api/email/campaigns');
    state.campaigns = data.campaigns || [];
    const list = document.getElementById('email-campaigns-list');
    document.getElementById('email-campaign-detail').style.display = 'none';
    list.style.display = 'block';

    if (state.campaigns.length === 0) {
      list.innerHTML = '<div class="empty-state"><i class="fas fa-rocket fa-3x muted"></i><p>No email campaigns yet. Click "New Campaign" to get started.</p></div>';
      return;
    }

    list.innerHTML = state.campaigns.map(c => {
      const s = c.stats || {};
      return `
        <div class="email-campaign-card" onclick="EmailModule.openCampaign(${c.id})">
          <div class="ecc-left">
            <div class="ecc-name">${escapeHtml(c.name)}</div>
            <div class="ecc-meta muted">
              <span class="status-pill status-${c.status}">${c.status}</span>
              ${c.message_count} steps · ${s.total_enrolled || 0} recipients
            </div>
          </div>
          <div class="ecc-stats">
            <div><strong>${s.sent || 0}</strong><span class="muted">sent</span></div>
            <div><strong>${s.open_rate || 0}%</strong><span class="muted">opens</span></div>
            <div><strong>${s.reply_rate || 0}%</strong><span class="muted">replies</span></div>
            <div><strong>${s.bounce_rate || 0}%</strong><span class="muted">bounces</span></div>
          </div>
        </div>
      `;
    }).join('');
  }

  async function openCampaign(id) {
    const data = await api(`/api/email/campaigns/${id}`);
    if (!data.success) return;
    const c = data.campaign;
    const list = document.getElementById('email-campaigns-list');
    const detail = document.getElementById('email-campaign-detail');
    list.style.display = 'none';
    detail.style.display = 'block';

    const s = c.stats || {};
    const lifecycleButtons = c.status === 'draft'
      ? `<button class="btn btn-success" onclick="EmailModule.startCampaign(${c.id})"><i class="fas fa-play"></i> Launch</button>`
      : c.status === 'active'
        ? `<button class="btn btn-warning" onclick="EmailModule.pauseCampaign(${c.id})"><i class="fas fa-pause"></i> Pause</button>`
        : c.status === 'paused'
          ? `<button class="btn btn-success" onclick="EmailModule.resumeCampaign(${c.id})"><i class="fas fa-play"></i> Resume</button>`
          : '';

    const canComplete = c.status === 'active' || c.status === 'paused';
    detail.innerHTML = `
      <div class="campaign-detail-header">
        <button class="btn btn-link" onclick="EmailModule.loadCampaignsList()">&larr; All campaigns</button>
        <h3>${escapeHtml(c.name)} <span class="status-pill status-${c.status}">${c.status}</span></h3>
        <div class="campaign-actions">
          ${lifecycleButtons}
          ${(c.status === 'active' || c.status === 'paused') ? `<button class="btn btn-secondary" onclick="EmailModule.openAddRecipients(${c.id})"><i class="fas fa-user-plus"></i> Add recipients</button>` : ''}
          <button class="btn btn-secondary" onclick="EmailModule.editCampaign(${c.id})"><i class="fas fa-pen"></i> Edit</button>
          <button class="btn btn-secondary" onclick="EmailModule.duplicateCampaign(${c.id})"><i class="fas fa-copy"></i> Duplicate</button>
          ${c.ai_personalization ? `<button class="btn btn-secondary" onclick="EmailModule.previewCampaignOpeners(${c.id})"><i class="fas fa-wand-magic-sparkles"></i> Preview openers</button>` : ''}
          ${canComplete ? `<button class="btn btn-secondary" onclick="EmailModule.completeCampaign(${c.id})"><i class="fas fa-flag-checkered"></i> Complete</button>` : ''}
          ${c.status === 'draft' ? `<button class="btn btn-danger" onclick="EmailModule.deleteCampaign(${c.id})"><i class="fas fa-trash"></i> Delete</button>` : ''}
        </div>
      </div>
      <div id="ec-detail-panel"></div>

      <div class="stats-grid">
        <div class="stat-card"><div class="stat-info"><span class="stat-value">${s.total_enrolled || 0}</span><span class="stat-label">Enrolled</span></div></div>
        <div class="stat-card"><div class="stat-info"><span class="stat-value">${s.sent || 0}</span><span class="stat-label">Sent</span></div></div>
        <div class="stat-card"><div class="stat-info"><span class="stat-value">${s.open_rate || 0}%</span><span class="stat-label">Opens</span></div></div>
        <div class="stat-card"><div class="stat-info"><span class="stat-value">${s.reply_rate || 0}%</span><span class="stat-label">Replies</span></div></div>
        <div class="stat-card"><div class="stat-info"><span class="stat-value">${s.bounce_rate || 0}%</span><span class="stat-label">Bounces</span></div></div>
        <div class="stat-card"><div class="stat-info"><span class="stat-value">${s.unsubscribed || 0}</span><span class="stat-label">Unsubs</span></div></div>
      </div>

      <div class="card">
        <h4>Sequence</h4>
        ${(c.messages || []).map((m, i) => `
          <div class="sequence-step">
            <div class="step-num">${i + 1}</div>
            <div class="step-body">
              <div><strong>${escapeHtml(m.subject)}</strong>${m.has_ab_test ? ' <span class="badge-ab">A/B</span>' : ''}</div>
              <div class="muted">${m.days_after_previous === 0 ? 'Sent immediately' : `+${m.days_after_previous} days after previous`}${m.same_thread ? ' · same thread' : ''}</div>
              ${m.stats ? `<div class="muted">${m.stats.sent || 0} sent · ${m.stats.open_rate || 0}% opens · ${m.stats.reply_rate || 0}% replies</div>` : ''}
            </div>
          </div>
        `).join('')}
      </div>

      <div class="card">
        <h4>Recipients (sample)</h4>
        <div id="ec-enrollment-table"></div>
      </div>
    `;

    // Load enrollments
    const en = await api(`/api/email/campaigns/${id}/enrollments?limit=50`);
    const tbl = document.getElementById('ec-enrollment-table');
    if (!en.enrollments || en.enrollments.length === 0) {
      tbl.innerHTML = '<p class="muted">No enrollments yet.</p>';
    } else {
      tbl.innerHTML = `
        <table class="data-table">
          <thead><tr><th>Email</th><th>Name</th><th>Step</th><th>Status</th><th>Last Sent</th><th>Engagement</th></tr></thead>
          <tbody>
          ${en.enrollments.map(e => `
            <tr>
              <td>${escapeHtml(e.email)}</td>
              <td>${escapeHtml(e.name || '')}</td>
              <td>${e.current_step}</td>
              <td><span class="status-pill status-${e.status}">${e.status}</span></td>
              <td>${fmtDate(e.last_sent_at)}</td>
              <td>${e.first_reply_at ? '💬 replied ' : ''}${e.open_count > 0 ? `👁 ${e.open_count} ` : ''}${e.click_count > 0 ? `🖱 ${e.click_count}` : ''}</td>
            </tr>
          `).join('')}
          </tbody>
        </table>
        <div class="muted">Showing ${en.enrollments.length} of ${en.total}</div>
      `;
    }
  }

  // ============ Inbox ============
  async function loadInbox() {
    const includeAuto = document.getElementById('email-include-auto').checked;
    const data = await api(`/api/email/inbox?include_auto=${includeAuto}`);
    state.inboxReplies = data.replies || [];
    const list = document.getElementById('email-inbox-list');
    if (state.inboxReplies.length === 0) {
      list.innerHTML = '<div class="empty-state"><i class="fas fa-inbox fa-3x muted"></i><p>No replies yet. The system polls Gmail every 2 minutes.</p></div>';
      return;
    }
    list.innerHTML = state.inboxReplies.map(r => `
      <div class="inbox-row ${r.read ? '' : 'unread'}" onclick="EmailModule.markRead(${r.id})">
        <div class="inbox-from">
          <strong>${escapeHtml(r.from_name || r.from_email)}</strong>
          <span class="muted">${escapeHtml(r.from_email)}</span>
          ${r.is_auto_reply ? '<span class="badge-auto">auto</span>' : ''}
        </div>
        <div class="inbox-subject">${escapeHtml(r.subject || '(no subject)')}</div>
        <div class="inbox-snippet muted">${escapeHtml(r.snippet || '')}</div>
        <div class="inbox-time muted">${fmtDate(r.received_at)}</div>
      </div>
    `).join('');
  }

  async function markRead(id) {
    await api(`/api/email/inbox/${id}/read`, { method: 'POST' });
    const row = document.querySelector(`.inbox-row[onclick*="(${id})"]`);
    if (row) row.classList.remove('unread');
  }

  // ============ Campaign Builder ============
  function newCampaign() {
    state.builder = {
      id: null,
      name: '',
      description: '',
      send_window_start: '09:00',
      send_window_end: '17:00',
      send_days: 'mon,tue,wed,thu,fri',
      sending_account_ids: [],
      ai_personalization: false,
      ai_prompt: '',
      track_opens: true,
      track_clicks: true,
      messages: [],
      contacts: [],
    };
    openBuilder();
  }

  async function editCampaign(id) {
    const data = await api(`/api/email/campaigns/${id}`);
    if (!data.success) return;
    state.builder = { ...data.campaign, contacts: [] };
    openBuilder();
  }

  async function openBuilder() {
    const b = state.builder;
    document.getElementById('email-campaign-modal-title').textContent = b.id ? 'Edit Campaign' : 'New Email Campaign';
    document.getElementById('ec-name').value = b.name || '';
    document.getElementById('ec-description').value = b.description || '';
    document.getElementById('ec-window-start').value = b.send_window_start || '09:00';
    document.getElementById('ec-window-end').value = b.send_window_end || '17:00';
    document.getElementById('ec-ai-toggle').checked = !!b.ai_personalization;
    document.getElementById('ec-ai-prompt').value = b.ai_prompt || '';
    document.getElementById('ec-ai-prompt-wrap').style.display = b.ai_personalization ? 'block' : 'none';
    document.getElementById('ec-track-opens').checked = b.track_opens !== false;
    document.getElementById('ec-track-clicks').checked = b.track_clicks !== false;
    document.getElementById('ec-paste-emails').value = '';
    document.getElementById('ec-enrollment-stats').textContent = '';

    // Send days checkboxes
    const activeDays = new Set((b.send_days || '').split(',').map(s => s.trim()));
    document.querySelectorAll('#ec-send-days input').forEach(cb => {
      cb.checked = activeDays.has(cb.value);
    });

    // Render account picker
    if (state.accounts.length === 0) await loadAccounts();
    const accPicker = document.getElementById('ec-account-picker');
    if (state.accounts.length === 0) {
      accPicker.innerHTML = '<p class="muted">No accounts connected. <a href="#" onclick="hideModal(\'email-campaign-modal\'); switchEmailTab(\'accounts\'); return false">Connect one first</a>.</p>';
    } else {
      const selected = new Set(b.sending_account_ids || []);
      accPicker.innerHTML = state.accounts.map(a => `
        <label class="account-pick">
          <input type="checkbox" value="${a.id}" ${selected.has(a.id) ? 'checked' : ''}>
          <span>${escapeHtml(a.email)} <span class="muted">(${a.daily_cap}/day)</span></span>
        </label>
      `).join('');
    }

    renderBuilderMessages();
    wireCSVDropzone();
    clearCSV();
    showModal('email-campaign-modal');
  }

  // Tokens that can be inserted into subject / body via chip click
  const VARIABLE_TOKENS = [
    { token: '{first_name}', label: 'first_name' },
    { token: '{name}', label: 'name' },
    { token: '{company}', label: 'company' },
    { token: '{email}', label: 'email' },
    { token: '{ai_first_line}', label: 'ai_first_line', ai: true },
    { token: '{spin:Hi|Hey|Hello}', label: 'spin:…' },
  ];

  // Track which textarea/input was last focused so chip clicks know where to insert
  let lastFocusedField = null;

  function renderBuilderMessages() {
    const wrap = document.getElementById('ec-messages-list');
    const msgs = state.builder.messages || [];
    if (msgs.length === 0) {
      wrap.innerHTML = '<p class="muted">No steps yet. Click "Add Step" to write your first email.</p>';
      return;
    }
    wrap.innerHTML = msgs.map((m, i) => `
      <div class="builder-message" data-idx="${i}">
        <div class="bm-header">
          <strong>Step ${i + 1}</strong>
          ${i > 0 ? `<span class="muted">+ <input type="number" min="0" value="${m.days_after_previous || 0}" data-bm="days_after_previous" style="width:50px"> days after previous</span>` : '<span class="muted">Sent immediately on launch</span>'}
          <button class="btn-icon btn-danger" onclick="EmailModule.removeBuilderMessage(${i})"><i class="fas fa-times"></i></button>
        </div>
        <input type="text" class="bm-subject" placeholder="Subject" data-bm="subject" value="${escapeHtml(m.subject || '')}">
        <input type="text" class="bm-subject-b" placeholder="Subject B (A/B test, optional)" data-bm="subject_variant_b" value="${escapeHtml(m.subject_variant_b || '')}">
        <textarea class="bm-body" rows="8" placeholder="Email body (HTML). Click variables below to insert them..." data-bm="body_html">${escapeHtml(m.body_html || '')}</textarea>
        <div class="variable-chips">
          <span class="variable-chips-label">Insert:</span>
          ${VARIABLE_TOKENS.map(v => `
            <button type="button" class="var-chip ${v.ai ? 'var-chip-ai' : ''}" data-token="${escapeHtml(v.token)}">${escapeHtml(v.label)}</button>
          `).join('')}
        </div>
        ${i > 0 ? `<label class="checkbox-label"><input type="checkbox" data-bm="same_thread" ${m.same_thread !== false ? 'checked' : ''}> Send in same thread (Re: ...)</label>` : ''}
      </div>
    `).join('');

    // Wire change handlers to keep state in sync
    wrap.querySelectorAll('.builder-message').forEach(node => {
      const idx = parseInt(node.dataset.idx, 10);
      node.querySelectorAll('[data-bm]').forEach(input => {
        input.addEventListener('input', () => {
          const field = input.dataset.bm;
          let val = input.value;
          if (input.type === 'checkbox') val = input.checked;
          if (input.type === 'number') val = parseInt(val, 10) || 0;
          state.builder.messages[idx][field] = val;
        });
        // Track focus so chip clicks know where to insert
        if (input.tagName === 'TEXTAREA' || (input.tagName === 'INPUT' && input.type === 'text')) {
          input.addEventListener('focus', () => { lastFocusedField = input; });
        }
      });

      // Wire variable chip clicks
      node.querySelectorAll('.var-chip').forEach(chip => {
        chip.addEventListener('mousedown', (e) => {
          // mousedown (not click) so focus doesn't move off the textarea
          e.preventDefault();
          const token = chip.dataset.token;
          // Prefer the focused field within THIS step's builder-message
          let target = lastFocusedField && node.contains(lastFocusedField) ? lastFocusedField : node.querySelector('.bm-body');
          insertAtCursor(target, token);
          // Update state from the modified value
          const field = target.dataset.bm;
          if (field) state.builder.messages[idx][field] = target.value;
        });
      });
    });
  }

  function insertAtCursor(field, text) {
    if (!field) return;
    field.focus();
    const start = field.selectionStart || 0;
    const end = field.selectionEnd || 0;
    const value = field.value || '';
    field.value = value.slice(0, start) + text + value.slice(end);
    const newPos = start + text.length;
    field.setSelectionRange(newPos, newPos);
    // Fire input event so any listeners pick up the change
    field.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function addBuilderMessage() {
    state.builder.messages.push({
      subject: '',
      body_html: '',
      days_after_previous: state.builder.messages.length === 0 ? 0 : 3,
      same_thread: true,
    });
    renderBuilderMessages();
  }

  function removeBuilderMessage(idx) {
    state.builder.messages.splice(idx, 1);
    renderBuilderMessages();
  }

  function collectBuilder() {
    const b = state.builder;
    b.name = document.getElementById('ec-name').value.trim();
    b.description = document.getElementById('ec-description').value;
    b.send_window_start = document.getElementById('ec-window-start').value;
    b.send_window_end = document.getElementById('ec-window-end').value;
    b.ai_personalization = document.getElementById('ec-ai-toggle').checked;
    b.ai_prompt = document.getElementById('ec-ai-prompt').value;
    b.track_opens = document.getElementById('ec-track-opens').checked;
    b.track_clicks = document.getElementById('ec-track-clicks').checked;
    b.send_days = Array.from(document.querySelectorAll('#ec-send-days input:checked')).map(c => c.value).join(',');
    b.sending_account_ids = Array.from(document.querySelectorAll('#ec-account-picker input:checked')).map(c => parseInt(c.value, 10));
    return b;
  }

  function parsePastedEmails(text) {
    return text.split(/\n/).map(line => {
      const parts = line.split(',').map(s => s.trim());
      const email = parts[0];
      if (!email || !email.includes('@')) return null;
      return { email, name: parts[1] || '', company: parts[2] || '' };
    }).filter(Boolean);
  }

  // ============ CSV upload + auto-mapping ============
  const csvState = {
    headers: [],
    rows: [],          // array of arrays
    mapping: {},       // { email: colIdx, name: colIdx, company: colIdx }
    rawText: '',
  };

  // Minimal RFC 4180-ish CSV parser (handles quotes & embedded commas/newlines)
  function parseCSV(text) {
    const rows = [];
    let row = [], field = '', i = 0, inQuotes = false;
    while (i < text.length) {
      const c = text[i];
      if (inQuotes) {
        if (c === '"' && text[i + 1] === '"') { field += '"'; i += 2; continue; }
        if (c === '"') { inQuotes = false; i++; continue; }
        field += c; i++; continue;
      }
      if (c === '"') { inQuotes = true; i++; continue; }
      if (c === ',') { row.push(field); field = ''; i++; continue; }
      if (c === '\r') { i++; continue; }
      if (c === '\n') { row.push(field); rows.push(row); row = []; field = ''; i++; continue; }
      field += c; i++;
    }
    if (field.length > 0 || row.length > 0) { row.push(field); rows.push(row); }
    return rows.filter(r => r.some(c => c && c.trim()));  // drop blank lines
  }

  // Fuzzy header matching — returns the column index that best matches each target
  function autodetectColumns(headers) {
    const norm = s => (s || '').toLowerCase().replace(/[\s_\-]/g, '');
    const headersN = headers.map(norm);

    // Patterns ordered by specificity
    const matchers = {
      email: ['email', 'emailaddress', 'mail', 'workemail', 'primaryemail'],
      name: ['fullname', 'name', 'contactname', 'ownername', 'recipientname'],
      first_name: ['firstname', 'fname', 'given', 'givenname'],
      last_name: ['lastname', 'lname', 'surname', 'family', 'familyname'],
      company: ['company', 'companyname', 'organization', 'organisation', 'business', 'businessname', 'employer', 'firm', 'account'],
    };

    const mapping = {};
    for (const [key, candidates] of Object.entries(matchers)) {
      for (const candidate of candidates) {
        const idx = headersN.findIndex(h => h === candidate);
        if (idx >= 0) { mapping[key] = idx; break; }
      }
      // Fallback: contains
      if (mapping[key] === undefined) {
        for (const candidate of candidates) {
          const idx = headersN.findIndex(h => h.includes(candidate));
          if (idx >= 0) { mapping[key] = idx; break; }
        }
      }
    }
    return mapping;
  }

  function handleCSVFile(file) {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      toast('CSV too large (max 10 MB)', 'error');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = reader.result;
        csvState.rawText = text;
        const rows = parseCSV(text);
        if (rows.length < 2) {
          toast('CSV needs at least a header row + 1 data row', 'error');
          return;
        }
        csvState.headers = rows[0];
        csvState.rows = rows.slice(1);
        csvState.mapping = autodetectColumns(csvState.headers);
        renderCSVMapping();
      } catch (e) {
        toast('Failed to parse CSV: ' + e.message, 'error');
      }
    };
    reader.onerror = () => toast('Failed to read file', 'error');
    reader.readAsText(file);
  }

  function renderCSVMapping() {
    const wrap = document.getElementById('ec-csv-mapping');
    wrap.style.display = 'block';

    const headerOpts = csvState.headers.map((h, i) => `<option value="${i}">${escapeHtml(h)}</option>`).join('');
    const opt = (key) => {
      const sel = csvState.mapping[key];
      return `<select data-csv-map="${key}">
        <option value="">— none —</option>
        ${csvState.headers.map((h, i) => `<option value="${i}" ${i === sel ? 'selected' : ''}>${escapeHtml(h)}</option>`).join('')}
      </select>`;
    };

    const detected = Object.keys(csvState.mapping).length;
    const status = csvState.mapping.email !== undefined
      ? `<span style="color:#065f46">✓ Auto-detected ${detected} column${detected === 1 ? '' : 's'} from ${csvState.rows.length} rows</span>`
      : `<span style="color:#92400e">⚠ Couldn't auto-detect the email column — pick it below</span>`;

    wrap.innerHTML = `
      <div class="csv-mapping-header">${status}</div>
      <div class="csv-mapping-row"><strong>Email</strong> <span>→</span> ${opt('email')}</div>
      <div class="csv-mapping-row"><strong>Name</strong> <span>→</span> ${opt('name')}</div>
      <div class="csv-mapping-row"><strong>First name</strong> <span>→</span> ${opt('first_name')}</div>
      <div class="csv-mapping-row"><strong>Last name</strong> <span>→</span> ${opt('last_name')}</div>
      <div class="csv-mapping-row"><strong>Company</strong> <span>→</span> ${opt('company')}</div>
      <div class="csv-preview">${csvState.rows.slice(0, 3).map(r => escapeHtml(r.join(' | '))).join('<br>')}</div>
      <div style="margin-top:10px;display:flex;gap:8px">
        <button type="button" class="btn btn-primary btn-sm" id="ec-csv-apply">Use ${csvState.rows.length} contacts from CSV</button>
        <button type="button" class="btn btn-secondary btn-sm" id="ec-csv-clear">Clear</button>
      </div>
    `;

    wrap.querySelectorAll('[data-csv-map]').forEach(sel => {
      sel.addEventListener('change', () => {
        const k = sel.dataset.csvMap;
        const v = sel.value;
        if (v === '') delete csvState.mapping[k];
        else csvState.mapping[k] = parseInt(v, 10);
      });
    });

    document.getElementById('ec-csv-apply').addEventListener('click', applyCSVToBuilder);
    document.getElementById('ec-csv-clear').addEventListener('click', clearCSV);
  }

  function csvRowsToContacts() {
    const m = csvState.mapping;
    if (m.email === undefined) {
      toast('You must map the email column', 'error');
      return [];
    }
    const contacts = [];
    for (const row of csvState.rows) {
      const email = (row[m.email] || '').trim();
      if (!email || !email.includes('@')) continue;
      const first = m.first_name !== undefined ? (row[m.first_name] || '').trim() : '';
      const last = m.last_name !== undefined ? (row[m.last_name] || '').trim() : '';
      let name = m.name !== undefined ? (row[m.name] || '').trim() : '';
      if (!name && (first || last)) name = `${first} ${last}`.trim();
      const company = m.company !== undefined ? (row[m.company] || '').trim() : '';

      // Preserve unmapped columns as extra_data
      const extra = {};
      csvState.headers.forEach((h, i) => {
        const mappedAs = Object.entries(m).find(([_, idx]) => idx === i);
        if (mappedAs) return;
        if (row[i] && row[i].trim()) extra[h.toLowerCase().replace(/\s+/g, '_')] = row[i].trim();
      });

      contacts.push({ email, name, company, ...extra });
    }
    return contacts;
  }

  // Stash CSV contacts on the builder until save
  function applyCSVToBuilder() {
    const contacts = csvRowsToContacts();
    if (contacts.length === 0) return;
    state.builder._csvContacts = contacts;
    document.getElementById('ec-enrollment-stats').textContent = `Ready to enroll ${contacts.length} contacts from CSV when you save`;
    toast(`${contacts.length} CSV contacts queued`, 'success');
  }

  function clearCSV() {
    csvState.headers = [];
    csvState.rows = [];
    csvState.mapping = {};
    csvState.rawText = '';
    delete state.builder._csvContacts;
    const wrap = document.getElementById('ec-csv-mapping');
    wrap.style.display = 'none';
    wrap.innerHTML = '';
    document.getElementById('ec-csv-file').value = '';
    document.getElementById('ec-enrollment-stats').textContent = '';
  }

  function wireCSVDropzone() {
    const dropzone = document.getElementById('ec-csv-dropzone');
    const fileInput = document.getElementById('ec-csv-file');
    const browseBtn = document.getElementById('ec-csv-browse');
    if (!dropzone || !fileInput) return;

    // Avoid double-wiring
    if (dropzone.dataset.wired) return;
    dropzone.dataset.wired = '1';

    browseBtn.addEventListener('click', (e) => { e.preventDefault(); fileInput.click(); });
    fileInput.addEventListener('change', () => handleCSVFile(fileInput.files[0]));

    ['dragenter', 'dragover'].forEach(ev => dropzone.addEventListener(ev, e => {
      e.preventDefault(); e.stopPropagation();
      dropzone.classList.add('drag-over');
    }));
    ['dragleave', 'drop'].forEach(ev => dropzone.addEventListener(ev, e => {
      e.preventDefault(); e.stopPropagation();
      dropzone.classList.remove('drag-over');
    }));
    dropzone.addEventListener('drop', e => {
      const file = e.dataTransfer.files[0];
      if (file) handleCSVFile(file);
    });
    dropzone.addEventListener('click', (e) => {
      if (e.target === browseBtn) return;
      fileInput.click();
    });
  }

  async function saveCampaign(launchAfter) {
    const b = collectBuilder();
    if (!b.name) return toast('Name required', 'error');
    if (b.messages.length === 0) return toast('Add at least one step', 'error');
    if (b.messages.some(m => !m.subject || !m.body_html)) return toast('Every step needs subject + body', 'error');
    if (launchAfter && b.sending_account_ids.length === 0) return toast('Pick at least one sending inbox', 'error');

    let campaignId = b.id;
    const payload = {
      name: b.name,
      description: b.description,
      send_window_start: b.send_window_start,
      send_window_end: b.send_window_end,
      send_days: b.send_days,
      sending_account_ids: b.sending_account_ids,
      ai_personalization: b.ai_personalization,
      ai_prompt: b.ai_prompt,
      track_opens: b.track_opens,
      track_clicks: b.track_clicks,
    };

    if (campaignId) {
      const r = await api(`/api/email/campaigns/${campaignId}`, { method: 'PUT', body: JSON.stringify(payload) });
      if (!r.success) return toast(r.error || 'Save failed', 'error');
    } else {
      const r = await api('/api/email/campaigns', { method: 'POST', body: JSON.stringify(payload) });
      if (!r.success) return toast(r.error || 'Save failed', 'error');
      campaignId = r.campaign.id;
      b.id = campaignId;
    }

    // Reconcile the sequence in a single diff-based call. Existing steps keep
    // their id so the server can edit-in-place instead of delete+recreate.
    const messagesPayload = b.messages.map((m, i) => ({
      id: m.id || undefined,
      subject: m.subject,
      body_html: m.body_html,
      days_after_previous: i === 0 ? 0 : (m.days_after_previous || 3),
      same_thread: m.same_thread !== false,
      subject_variant_b: m.subject_variant_b || null,
    }));
    const syncResp = await api(`/api/email/campaigns/${campaignId}/messages/sync`, {
      method: 'PUT',
      body: JSON.stringify({ messages: messagesPayload }),
    });
    if (syncResp.success && syncResp.result && syncResp.result.blocked && syncResp.result.blocked.length) {
      const blocked = syncResp.result.blocked;
      toast(`${blocked.length} step change(s) blocked: ${blocked.map(b => 'step ' + b.sequence_order + ' (' + b.reason + ')').join(', ')}`, 'error');
    }

    // Enroll: combine pasted + CSV contacts
    const pasted = parsePastedEmails(document.getElementById('ec-paste-emails').value);
    const fromCsv = state.builder._csvContacts || [];
    const allNew = [...pasted, ...fromCsv];
    if (allNew.length > 0) {
      const er = await api(`/api/email/campaigns/${campaignId}/enroll`, {
        method: 'POST', body: JSON.stringify({ contacts: allNew }),
      });
      if (er.success) {
        const s = er.stats || {};
        const parts = [`Enrolled ${s.enrolled || er.enrolled} contacts`];
        if (s.enriched_count) parts.push(`${s.enriched_count} enriched from leads DB`);
        const skipped = (s.skipped_duplicate || 0) + (s.skipped_invalid || 0) + (s.skipped_unsubscribed || 0);
        if (skipped) parts.push(`${skipped} skipped (dup/invalid/unsub)`);
        toast(parts.join(' · '), 'success');
      }
    }

    if (launchAfter) {
      const r = await api(`/api/email/campaigns/${campaignId}/start`, { method: 'POST' });
      if (!r.success) {
        toast(r.error || 'Launch failed', 'error');
      } else {
        toast('Campaign launched', 'success');
      }
    } else {
      toast('Draft saved', 'success');
    }

    hideModal('email-campaign-modal');
    loadCampaignsList();
  }

  async function pullLeadsEmails() {
    if (!state.builder.id) {
      toast('Save the campaign as a draft first, then pull leads', 'error');
      return;
    }
    const r = await api(`/api/email/campaigns/${state.builder.id}/enroll`, {
      method: 'POST', body: JSON.stringify({ use_filters: true }),
    });
    if (r.success) {
      const s = r.stats || {};
      const wrap = document.getElementById('ec-enrollment-stats');
      wrap.className = 'enrollment-feedback';
      wrap.innerHTML = `
        <strong>${s.enrolled || r.enrolled} contacts enrolled</strong> from leads DB.
        ${s.enriched_count ? ` <span>${s.enriched_count} got extra permit/owner context</span>` : ''}
        ${(s.skipped_duplicate + s.skipped_unsubscribed + s.skipped_invalid) > 0 ? `<div class="skipped">Skipped: ${s.skipped_duplicate || 0} duplicate, ${s.skipped_unsubscribed || 0} unsubscribed, ${s.skipped_invalid || 0} invalid</div>` : ''}
      `;
      toast(`Enrolled ${s.enrolled || r.enrolled} contacts`, 'success');
    } else {
      toast(r.error || 'Pull failed', 'error');
    }
  }

  async function startCampaign(id) {
    const r = await api(`/api/email/campaigns/${id}/start`, { method: 'POST' });
    if (r.success) { toast('Launched', 'success'); openCampaign(id); }
    else toast(r.error || 'Failed', 'error');
  }
  async function pauseCampaign(id) {
    const r = await api(`/api/email/campaigns/${id}/pause`, { method: 'POST' });
    if (r.success) { toast('Paused', 'success'); openCampaign(id); }
  }
  async function resumeCampaign(id) {
    const r = await api(`/api/email/campaigns/${id}/resume`, { method: 'POST' });
    if (r.success) { toast('Resumed', 'success'); openCampaign(id); }
  }
  async function deleteCampaign(id) {
    if (!confirm('Delete this campaign and all its data?')) return;
    const r = await api(`/api/email/campaigns/${id}`, { method: 'DELETE' });
    if (r.success) { toast('Deleted', 'success'); loadCampaignsList(); }
  }
  async function completeCampaign(id) {
    if (!confirm('Mark this campaign complete? Remaining steps will stop sending.')) return;
    const r = await api(`/api/email/campaigns/${id}/complete`, { method: 'POST' });
    if (r.success) { toast('Campaign completed', 'success'); openCampaign(id); }
    else toast(r.error || 'Failed', 'error');
  }
  async function duplicateCampaign(id) {
    const r = await api(`/api/email/campaigns/${id}/duplicate`, { method: 'POST' });
    if (r.success) {
      toast('Duplicated as draft — opening copy', 'success');
      openCampaign(r.campaign.id);
    } else toast(r.error || 'Failed', 'error');
  }

  // Inline "add recipients to a running campaign" panel
  function openAddRecipients(id) {
    const panel = document.getElementById('ec-detail-panel');
    if (!panel) return;
    panel.innerHTML = `
      <div class="card add-recipients-panel">
        <h4>Add recipients to this campaign</h4>
        <p class="muted">New contacts enter at step 1 and flow through the sequence. Duplicates and unsubscribes are skipped automatically.</p>
        <textarea id="ar-paste" rows="4" placeholder="One per line, optionally: email,name,company"></textarea>
        <div class="add-recipients-actions">
          <button class="btn btn-secondary btn-sm" onclick="EmailModule.addRecipientsFromLeads(${id})"><i class="fas fa-database"></i> Pull from leads DB</button>
          <button class="btn btn-primary btn-sm" onclick="EmailModule.submitAddRecipients(${id})">Add pasted contacts</button>
          <button class="btn btn-link btn-sm" onclick="document.getElementById('ec-detail-panel').innerHTML=''">Close</button>
        </div>
        <div id="ar-feedback" class="muted"></div>
      </div>`;
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  async function submitAddRecipients(id) {
    const text = document.getElementById('ar-paste').value;
    const contacts = parsePastedEmails(text);
    if (contacts.length === 0) { toast('No valid emails pasted', 'error'); return; }
    const r = await api(`/api/email/campaigns/${id}/enroll`, {
      method: 'POST', body: JSON.stringify({ contacts }),
    });
    showAddRecipientFeedback(r);
  }
  async function addRecipientsFromLeads(id) {
    const r = await api(`/api/email/campaigns/${id}/enroll`, {
      method: 'POST', body: JSON.stringify({ use_filters: true }),
    });
    showAddRecipientFeedback(r);
  }
  function showAddRecipientFeedback(r) {
    const fb = document.getElementById('ar-feedback');
    if (!r.success) { if (fb) fb.textContent = r.error || 'Failed'; toast(r.error || 'Failed', 'error'); return; }
    const s = r.stats || {};
    if (fb) {
      fb.className = 'enrollment-feedback';
      fb.innerHTML = `<strong>${s.enrolled || r.enrolled} added</strong>${s.enriched_count ? ` · ${s.enriched_count} enriched` : ''}${(s.skipped_duplicate + s.skipped_unsubscribed + s.skipped_invalid) ? ` · ${(s.skipped_duplicate||0)+(s.skipped_unsubscribed||0)+(s.skipped_invalid||0)} skipped` : ''}`;
    }
    toast(`Added ${s.enrolled || r.enrolled} recipients`, 'success');
  }

  // Batch opener preview — shows real openers for enrolled contacts
  async function previewCampaignOpeners(id) {
    const panel = document.getElementById('ec-detail-panel');
    if (!panel) return;
    panel.innerHTML = '<div class="card"><div class="muted">Generating sample openers…</div></div>';
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    const r = await api(`/api/email/campaigns/${id}/preview-openers`, {
      method: 'POST', body: JSON.stringify({ n: 5 }),
    });
    if (!r.success) {
      panel.innerHTML = `<div class="card ai-preview-result empty">${escapeHtml(r.error || 'Failed')}</div>`;
      return;
    }
    panel.innerHTML = `
      <div class="card">
        <h4>Sample AI openers <button class="btn btn-link btn-sm" onclick="document.getElementById('ec-detail-panel').innerHTML=''">Close</button></h4>
        ${r.previews.map(p => `
          <div class="opener-sample">
            <div class="opener-sample-to">${escapeHtml(p.name || p.email)} <span class="muted">${escapeHtml(p.email)}</span></div>
            ${p.opener ? `<div class="opener-sample-text">"${escapeHtml(p.opener)}"</div>` : '<div class="muted">⚠ empty — too little context, {ai_first_line} will be blank</div>'}
          </div>
        `).join('')}
      </div>`;
  }

  // ============ Event wiring ============
  let _initialized = false;
  function init() {
    if (_initialized) return;
    _initialized = true;
    // Email subnav tabs
    document.querySelectorAll('.email-tab').forEach(b => {
      b.addEventListener('click', () => switchEmailTab(b.dataset.emailTab));
    });

    document.getElementById('connect-email-account-btn')?.addEventListener('click', connectAccount);
    document.getElementById('new-email-campaign-btn')?.addEventListener('click', newCampaign);
    document.getElementById('email-include-auto')?.addEventListener('change', loadInbox);
    document.getElementById('ec-add-message-btn')?.addEventListener('click', addBuilderMessage);
    document.getElementById('ec-save-btn')?.addEventListener('click', () => saveCampaign(false));
    document.getElementById('ec-launch-btn')?.addEventListener('click', () => saveCampaign(true));
    document.getElementById('ec-pull-leads-btn')?.addEventListener('click', pullLeadsEmails);
    document.getElementById('ec-ai-toggle')?.addEventListener('change', e => {
      document.getElementById('ec-ai-prompt-wrap').style.display = e.target.checked ? 'block' : 'none';
    });
    document.getElementById('ec-ai-preview-btn')?.addEventListener('click', previewAIOpener);
  }

  async function previewAIOpener() {
    const email = document.getElementById('ec-ai-preview-email').value.trim();
    const prompt = document.getElementById('ec-ai-prompt').value.trim();
    const wrap = document.getElementById('ec-ai-preview-result');

    if (!email || !email.includes('@')) {
      toast('Enter an email to test with', 'error');
      return;
    }

    wrap.style.display = 'block';
    wrap.className = 'ai-preview-result';
    wrap.innerHTML = '<div class="muted">Generating preview…</div>';

    const data = await api('/api/email/preview-opener', {
      method: 'POST',
      body: JSON.stringify({ prompt, sample_email: email }),
    });

    if (!data.success) {
      wrap.className = 'ai-preview-result empty';
      wrap.innerHTML = `<div><strong>Error:</strong> ${escapeHtml(data.error || 'Unknown')}</div>`;
      if (data.context) {
        wrap.innerHTML += `<div class="ai-preview-result-context">Context that would be sent:\n${escapeHtml(JSON.stringify(data.context, null, 2))}</div>`;
      }
      return;
    }

    const ctx = data.context || {};
    const ctxText = JSON.stringify(ctx, null, 2);
    const enrichedKeys = Object.keys(ctx).filter(k => k.startsWith('recent_') || k === 'permit_count' || k === 'active_boroughs');

    if (data.is_empty) {
      wrap.className = 'ai-preview-result empty';
      wrap.innerHTML = `
        <div><strong>⚠ AI returned empty</strong> — the recipient had too little context, so {ai_first_line} will be blank in the email.</div>
        <div class="muted" style="margin-top:4px">Either remove {ai_first_line} from your body, or add more enriched data (try uploading a CSV with permit details).</div>
        <div class="ai-preview-result-context">${escapeHtml(ctxText)}</div>
      `;
    } else {
      wrap.innerHTML = `
        <div class="ai-preview-result-opener">"${escapeHtml(data.opener)}"</div>
        <div class="muted" style="font-size:12px">${enrichedKeys.length > 0 ? `✓ Found ${enrichedKeys.length} enrichment fields from your leads DB` : '⚠ No enrichment from leads DB — opener written from email alone'}</div>
        <div class="ai-preview-result-context">${escapeHtml(ctxText)}</div>
      `;
    }
  }

  // Public API
  window.EmailModule = {
    load: () => { init(); loadOverview(); loadAccounts(); },
    loadCampaignsList,
    openCampaign,
    editCampaign,
    deleteCampaign,
    startCampaign,
    pauseCampaign,
    resumeCampaign,
    completeCampaign,
    duplicateCampaign,
    openAddRecipients,
    submitAddRecipients,
    addRecipientsFromLeads,
    previewCampaignOpeners,
    saveAccount,
    deleteAccount,
    markRead,
    addBuilderMessage,
    removeBuilderMessage,
  };

  // Init once at DOM ready as a safety net
  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);

  // Poll for unread badge every 60s globally
  setInterval(async () => {
    try {
      const data = await api('/api/email/stats');
      if (data.success) {
        const badge = document.getElementById('email-unread-badge');
        const n = data.stats?.unread_replies || 0;
        if (n > 0) { badge.style.display = 'inline-block'; badge.textContent = n; }
        else { badge.style.display = 'none'; }
      }
    } catch {}
  }, 60000);
})();
