// ============ API Service ============
const API = {
    async get(endpoint) {
        const response = await fetch(`/api${endpoint}`);
        return response.json();
    },
    
    async post(endpoint, data) {
        const response = await fetch(`/api${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    async put(endpoint, data) {
        const response = await fetch(`/api${endpoint}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return response.json();
    },
    
    async delete(endpoint) {
        const response = await fetch(`/api${endpoint}`, { method: 'DELETE' });
        return response.json();
    }
};

// ============ State ============
const state = {
    contacts: [],
    conversations: [],
    templates: [],
    selectedContacts: [],
    currentConversation: null
};

// ============ Utilities ============
function formatDate(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    
    return date.toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit'
    });
}

function formatTime(dateString) {
    if (!dateString) return '';
    return new Date(dateString).toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit'
    });
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;
    setTimeout(() => toast.classList.remove('show'), 3000);
}

function showModal(modalId) {
    document.getElementById(modalId).classList.add('active');
}

function hideModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

// ============ Navigation ============
function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const view = item.dataset.view;
            
            // Update nav
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            
            // Show view
            document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
            document.getElementById(`${view}-view`).classList.add('active');
            
            // Load data for view
            loadViewData(view);
        });
    });
}

async function loadViewData(view) {
    switch (view) {
        case 'dashboard':
            await loadDashboard();
            break;
        case 'conversations':
            await loadConversations();
            break;
        case 'contacts':
            await loadContacts();
            break;
        case 'compose':
            await loadComposeView();
            break;
        case 'scheduled':
            await loadScheduled();
            break;
        case 'templates':
            await loadTemplates();
            break;
    }
}

// ============ Dashboard ============
async function loadDashboard() {
    // Load stats
    const statsResponse = await API.get('/stats');
    if (statsResponse.success) {
        const stats = statsResponse.stats;
        document.getElementById('stat-contacts').textContent = stats.total_contacts;
        document.getElementById('stat-total').textContent = stats.total_messages;
        document.getElementById('stat-sent').textContent = stats.sent_messages;
        document.getElementById('stat-received').textContent = stats.received_messages;
    }
    
    // Load recent messages
    const messagesResponse = await API.get('/messages?limit=10');
    if (messagesResponse.success) {
        renderRecentMessages(messagesResponse.messages);
    }
}

function renderRecentMessages(messages) {
    const container = document.getElementById('recent-messages');
    
    if (messages.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-inbox"></i>
                <p>No messages yet</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = messages.map(msg => `
        <div class="message-item">
            <div class="message-info">
                <div class="message-phone">${msg.contact?.name || msg.phone_number}</div>
                <div class="message-body">${msg.body}</div>
            </div>
            <div class="message-meta">
                <div class="message-time">${formatDate(msg.created_at)}</div>
                <span class="message-status status-${msg.status}">${msg.status}</span>
            </div>
        </div>
    `).join('');
}

// ============ Conversations ============
async function loadConversations() {
    const response = await API.get('/conversations');
    if (response.success) {
        state.conversations = response.conversations;
        renderConversationList();
    }
}

function renderConversationList() {
    const container = document.getElementById('conversation-list');
    
    if (state.conversations.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-comments"></i>
                <p>No conversations yet</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = state.conversations.map(conv => {
        const name = conv.contact?.name;
        const phone = conv.phone_number;
        return `
        <div class="conversation-item" data-phone="${phone}">
            <span class="conversation-time">${formatDate(conv.last_message.created_at)}</span>
            <div class="conversation-contact">
                ${name ? `<span class="contact-name">${name}</span>` : ''}
                <span class="contact-phone ${name ? 'small' : ''}">${phone}</span>
            </div>
            <div class="conversation-preview">${conv.last_message.body}</div>
        </div>
    `}).join('');
    
    // Add click handlers
    container.querySelectorAll('.conversation-item').forEach(item => {
        item.addEventListener('click', () => {
            container.querySelectorAll('.conversation-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            loadConversation(item.dataset.phone);
        });
    });
}

async function loadConversation(phone) {
    state.currentConversation = phone;
    
    const response = await API.get(`/conversations/${encodeURIComponent(phone)}`);
    if (response.success) {
        renderConversationMessages(response.messages, phone);
    }
}

function renderConversationMessages(messages, phone) {
    // Find contact name
    const conv = state.conversations.find(c => c.phone_number === phone);
    const name = conv?.contact?.name;
    
    // Update header - show name prominently with phone smaller
    document.getElementById('conversation-header').innerHTML = name 
        ? `<strong>${name}</strong><small style="color: var(--text-secondary); margin-left: 12px; font-weight: normal;">${phone}</small>`
        : `<strong>${phone}</strong>`;
    
    // Render messages
    const container = document.getElementById('conversation-messages');
    container.innerHTML = messages.map(msg => `
        <div class="chat-bubble ${msg.direction}">
            <div>${msg.body}</div>
            <div class="chat-time">${formatTime(msg.created_at)}</div>
        </div>
    `).join('');
    
    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
    
    // Show reply area
    document.getElementById('conversation-reply').style.display = 'flex';
}

async function sendReply() {
    const input = document.getElementById('reply-input');
    const body = input.value.trim();
    
    if (!body || !state.currentConversation) return;
    
    const response = await API.post('/messages/send', {
        to: state.currentConversation,
        body: body
    });
    
    if (response.success) {
        input.value = '';
        await loadConversation(state.currentConversation);
        showToast('Reply sent');
    } else {
        showToast(response.error || 'Failed to send', 'error');
    }
}

// ============ Contacts ============
// State for contact tabs
state.contactsTab = 'leads';  // 'leads' or 'manual'

async function loadContacts(search = '', offset = 0) {
    if (state.contactsTab === 'manual') {
        await loadManualContacts();
        return;
    }
    
    const mobileOnly = document.getElementById('mobile-only-filter')?.checked ?? true;
    
    let endpoint = `/contacts?limit=100&offset=${offset}&mobile_only=${mobileOnly}`;
    if (search) {
        endpoint += `&search=${encodeURIComponent(search)}`;
    }
    
    const response = await API.get(endpoint);
    
    if (response.success) {
        state.contacts = response.contacts;
        state.contactsTotal = response.total;
        state.contactsOffset = offset;
        renderContactsTable();
        renderContactsPagination();
    }
}

async function loadManualContacts() {
    const response = await API.get('/contacts/manual');
    
    if (response.success) {
        state.contacts = response.contacts;
        state.contactsTotal = response.total;
        state.contactsOffset = 0;
        renderContactsTable();
        renderContactsPagination();
    }
}

function renderContactsTable() {
    const tbody = document.getElementById('contacts-table-body');
    const actionsCol = document.getElementById('actions-col');
    const isManual = state.contactsTab === 'manual';
    
    // Show/hide actions column based on tab
    if (actionsCol) {
        actionsCol.style.display = isManual ? '' : 'none';
    }
    
    if (state.contacts.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="${isManual ? 7 : 6}" class="empty-state">
                    <i class="fas fa-address-book"></i>
                    <p>No contacts found</p>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = state.contacts.map(contact => `
        <tr>
            <td><input type="checkbox" class="contact-select" data-phone="${contact.phone_number || contact.phone}"></td>
            <td>${contact.name || '-'}</td>
            <td>${contact.phone_number || contact.phone}</td>
            <td>${contact.company || '-'}</td>
            <td>${contact.role || '-'}</td>
            <td><span class="badge badge-${contact.source}">${contact.source || 'permit'}</span></td>
            ${isManual ? `
                <td>
                    <button class="btn btn-sm btn-secondary edit-contact" data-id="${contact.id}" title="Edit">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-danger delete-contact" data-id="${contact.id}" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            ` : ''}
        </tr>
    `).join('');
    
    // Add event handlers for manual contacts
    if (isManual) {
        tbody.querySelectorAll('.edit-contact').forEach(btn => {
            btn.addEventListener('click', () => editContact(parseInt(btn.dataset.id)));
        });
        tbody.querySelectorAll('.delete-contact').forEach(btn => {
            btn.addEventListener('click', () => deleteContact(parseInt(btn.dataset.id)));
        });
    }
}

function renderContactsPagination() {
    const container = document.getElementById('contacts-pagination');
    const total = state.contactsTotal || 0;
    const offset = state.contactsOffset || 0;
    const limit = 100;
    const currentPage = Math.floor(offset / limit) + 1;
    const totalPages = Math.ceil(total / limit);
    
    // For manual contacts, don't show pagination
    if (state.contactsTab === 'manual') {
        container.innerHTML = `<span style="color: var(--text-secondary);">${total.toLocaleString()} manual contacts</span>`;
        return;
    }
    
    if (totalPages <= 1) {
        container.innerHTML = `<span style="color: var(--text-secondary);">${total.toLocaleString()} contacts</span>`;
        return;
    }
    
    container.innerHTML = `
        <button class="btn btn-sm btn-secondary" ${currentPage === 1 ? 'disabled' : ''} onclick="loadContacts('', ${offset - limit})">
            <i class="fas fa-chevron-left"></i> Prev
        </button>
        <span style="margin: 0 16px; color: var(--text-secondary);">
            Page ${currentPage} of ${totalPages} (${total.toLocaleString()} contacts)
        </span>
        <button class="btn btn-sm btn-secondary" ${currentPage === totalPages ? 'disabled' : ''} onclick="loadContacts('', ${offset + limit})">
            Next <i class="fas fa-chevron-right"></i>
        </button>
    `;
}

// ============ Manual Contacts CRUD ============

function openAddContactModal() {
    document.getElementById('contact-modal-title').textContent = 'Add Contact';
    document.getElementById('contact-form').reset();
    document.getElementById('contact-edit-id').value = '';
    showModal('contact-modal');
}

function editContact(contactId) {
    const contact = state.contacts.find(c => c.id === contactId);
    if (!contact) return;
    
    document.getElementById('contact-modal-title').textContent = 'Edit Contact';
    document.getElementById('contact-edit-id').value = contactId;
    document.getElementById('contact-phone').value = contact.phone || contact.phone_number || '';
    document.getElementById('contact-name').value = contact.name || '';
    document.getElementById('contact-company').value = contact.company || '';
    document.getElementById('contact-role').value = contact.role || '';
    document.getElementById('contact-notes').value = contact.notes || '';
    showModal('contact-modal');
}

async function saveContact() {
    const editId = document.getElementById('contact-edit-id').value;
    const data = {
        phone: document.getElementById('contact-phone').value.trim(),
        name: document.getElementById('contact-name').value.trim(),
        company: document.getElementById('contact-company').value.trim(),
        role: document.getElementById('contact-role').value.trim(),
        notes: document.getElementById('contact-notes').value.trim()
    };
    
    if (!data.phone) {
        showToast('Phone number is required', 'error');
        return;
    }
    
    let response;
    if (editId) {
        response = await API.put(`/contacts/manual/${editId}`, data);
    } else {
        response = await API.post('/contacts/manual', data);
    }
    
    if (response.success) {
        hideModal('contact-modal');
        showToast(editId ? 'Contact updated' : 'Contact added');
        await loadManualContacts();
    } else {
        showToast(response.error || 'Failed to save contact', 'error');
    }
}

async function deleteContact(contactId) {
    if (!confirm('Are you sure you want to delete this contact?')) return;
    
    const response = await API.delete(`/contacts/manual/${contactId}`);
    
    if (response.success) {
        showToast('Contact deleted');
        await loadManualContacts();
    } else {
        showToast(response.error || 'Failed to delete contact', 'error');
    }
}

// ============ CSV Upload ============

let csvFileData = null;

function previewCSV(file) {
    const reader = new FileReader();
    reader.onload = function(e) {
        csvFileData = e.target.result;
        const lines = csvFileData.split('\n').slice(0, 6);  // Header + 5 rows
        const previewContent = document.getElementById('csv-preview-content');
        previewContent.innerHTML = `<pre style="margin: 0; white-space: pre-wrap;">${lines.join('\n')}</pre>`;
        document.getElementById('csv-preview').style.display = 'block';
        document.getElementById('upload-csv-submit').disabled = false;
    };
    reader.readAsText(file);
}

async function uploadCSV() {
    if (!csvFileData) {
        showToast('No file selected', 'error');
        return;
    }
    
    const response = await API.post('/contacts/manual/upload', { csv_data: csvFileData });
    
    if (response.success) {
        hideModal('csv-modal');
        showToast(`Added ${response.added} contacts, skipped ${response.skipped}`);
        if (response.errors && response.errors.length > 0) {
            console.log('CSV upload errors:', response.errors);
        }
        // Switch to manual tab and reload
        state.contactsTab = 'manual';
        updateContactsTabs();
        await loadManualContacts();
    } else {
        showToast(response.error || 'Failed to upload CSV', 'error');
    }
}

function updateContactsTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === state.contactsTab);
    });
}

// ============ Compose ============
// ============ Compose ============

// SAFETY: Maximum recipients
const MAX_RECIPIENTS = 50;

async function loadComposeView() {
    // Load contacts for selector (mobile only for SMS)
    const response = await API.get('/contacts?mobile_only=true&limit=500');
    const contacts = response.success ? response.contacts : [];
    
    // Load templates
    await loadTemplates();
    
    // Populate contact selector with phone numbers
    const selector = document.getElementById('contact-selector');
    selector.innerHTML = contacts.map(c => `
        <label class="contact-checkbox">
            <input type="checkbox" value="${c.phone}" onchange="updateSelectedCount()">
            ${c.name || c.phone} ${c.role ? `(${c.role})` : ''}
        </label>
    `).join('');
    
    // Populate template dropdown
    const templateSelect = document.getElementById('message-template');
    templateSelect.innerHTML = '<option value="">-- Select Template --</option>' +
        state.templates.map(t => `<option value="${t.id}">${t.name}</option>`).join('');
    
    updateSelectedCount();
}

function updateSelectedCount() {
    const selected = document.querySelectorAll('#contact-selector input:checked').length;
    const countEl = document.getElementById('selected-count');
    if (countEl) {
        countEl.textContent = `(${selected} selected, max ${MAX_RECIPIENTS})`;
        countEl.style.color = selected > MAX_RECIPIENTS ? '#dc2626' : 'var(--text-secondary)';
    }
}

async function sendMessage() {
    const recipientType = document.querySelector('input[name="recipient-type"]:checked').value;
    const body = document.getElementById('message-body').value.trim();
    const isScheduled = document.getElementById('schedule-message').checked;
    
    if (!body) {
        showToast('Please enter a message', 'error');
        return;
    }
    
    // SAFETY: Get phone numbers based on selection
    let phoneNumbers = [];
    
    if (recipientType === 'single') {
        const phone = document.getElementById('single-number').value.trim();
        if (!phone) {
            showToast('Please enter a phone number', 'error');
            return;
        }
        phoneNumbers = [phone];
    } else if (recipientType === 'selected') {
        phoneNumbers = Array.from(
            document.querySelectorAll('#contact-selector input:checked')
        ).map(cb => cb.value);
        
        if (phoneNumbers.length === 0) {
            showToast('Please select at least one contact', 'error');
            return;
        }
    }
    
    // SAFETY: Check recipient count
    if (phoneNumbers.length > MAX_RECIPIENTS) {
        showToast(`SAFETY: Too many recipients (${phoneNumbers.length}). Maximum is ${MAX_RECIPIENTS}.`, 'error');
        return;
    }
    
    if (isScheduled) {
        // Schedule message - REQUIRES phone_numbers
        const name = document.getElementById('schedule-name').value.trim();
        const datetime = document.getElementById('schedule-datetime').value;
        
        if (!name || !datetime) {
            showToast('Please fill in schedule details', 'error');
            return;
        }
        
        if (phoneNumbers.length === 0) {
            showToast('SAFETY: You must select specific recipients to schedule a message', 'error');
            return;
        }
        
        // SAFETY: Confirmation for scheduling
        const confirmed = confirm(`Schedule message to ${phoneNumbers.length} recipient(s)?\\n\\nThis will send at: ${new Date(datetime).toLocaleString()}`);
        if (!confirmed) return;
        
        const response = await API.post('/scheduled', {
            name,
            body,
            scheduled_at: new Date(datetime).toISOString(),
            phone_numbers: phoneNumbers  // REQUIRED
        });
        
        if (response.success) {
            showToast(`Message scheduled to ${phoneNumbers.length} recipients`);
            document.getElementById('message-body').value = '';
            document.getElementById('schedule-name').value = '';
            document.getElementById('schedule-datetime').value = '';
        } else {
            showToast(response.error || 'Failed to schedule', 'error');
        }
        return;
    }
    
    // Send now - confirmation for bulk
    if (phoneNumbers.length > 1) {
        const confirmed = confirm(`Send message to ${phoneNumbers.length} recipient(s) NOW?`);
        if (!confirmed) return;
    }
    
    let response;
    
    if (phoneNumbers.length === 1) {
        response = await API.post('/messages/send', { to: phoneNumbers[0], body });
    } else {
        response = await API.post('/messages/bulk', { phone_numbers: phoneNumbers, body });
    }
    
    if (response.success) {
        const sent = response.sent || 1;
        const failed = response.failed || 0;
        showToast(`Sent: ${sent}, Failed: ${failed}`);
        document.getElementById('message-body').value = '';
        updateCharCount();
    } else {
        showToast(response.error || 'Failed to send', 'error');
    }
}

function updateCharCount() {
    const body = document.getElementById('message-body').value;
    document.getElementById('char-count').textContent = body.length;
}

// ============ Scheduled ============
async function loadScheduled() {
    const response = await API.get('/scheduled');
    if (response.success) {
        renderScheduledList(response.scheduled);
    }
}

function renderScheduledList(scheduled) {
    const container = document.getElementById('scheduled-list');
    
    if (scheduled.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-clock"></i>
                <p>No scheduled messages</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = scheduled.map(item => `
        <div class="scheduled-item">
            <div class="scheduled-info">
                <h4>${item.name}</h4>
                <p><i class="fas fa-calendar"></i> ${new Date(item.scheduled_at).toLocaleString()}</p>
                <p><i class="fas fa-users"></i> ${item.total_recipients} recipients</p>
                <p>${item.body.substring(0, 100)}${item.body.length > 100 ? '...' : ''}</p>
                <span class="scheduled-status ${item.status}">${item.status}</span>
            </div>
            ${item.status === 'pending' ? `
                <button class="btn btn-danger btn-sm cancel-scheduled" data-id="${item.id}">
                    <i class="fas fa-times"></i> Cancel
                </button>
            ` : ''}
        </div>
    `).join('');
    
    // Add cancel handlers
    container.querySelectorAll('.cancel-scheduled').forEach(btn => {
        btn.addEventListener('click', async () => {
            const response = await API.delete(`/scheduled/${btn.dataset.id}`);
            if (response.success) {
                await loadScheduled();
                showToast('Scheduled message cancelled');
            }
        });
    });
}

// ============ Templates ============
async function loadTemplates() {
    const response = await API.get('/templates');
    if (response.success) {
        state.templates = response.templates;
        renderTemplatesList();
    }
}

function renderTemplatesList() {
    const container = document.getElementById('templates-list');
    
    if (state.templates.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-file-alt"></i>
                <p>No templates yet</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = state.templates.map(template => `
        <div class="template-card">
            <h4>${template.name}</h4>
            <p>${template.body}</p>
            <div class="template-actions">
                <button class="btn btn-sm btn-primary use-template" data-body="${encodeURIComponent(template.body)}">
                    Use
                </button>
                <button class="btn btn-sm btn-danger delete-template" data-id="${template.id}">
                    Delete
                </button>
            </div>
        </div>
    `).join('');
    
    // Add handlers
    container.querySelectorAll('.use-template').forEach(btn => {
        btn.addEventListener('click', () => {
            document.getElementById('message-body').value = decodeURIComponent(btn.dataset.body);
            updateCharCount();
            document.querySelector('[data-view="compose"]').click();
        });
    });
    
    container.querySelectorAll('.delete-template').forEach(btn => {
        btn.addEventListener('click', async () => {
            const response = await API.delete(`/templates/${btn.dataset.id}`);
            if (response.success) {
                await loadTemplates();
                showToast('Template deleted');
            }
        });
    });
}

async function saveTemplate() {
    const name = document.getElementById('template-name').value.trim();
    const body = document.getElementById('template-body').value.trim();
    
    if (!name || !body) {
        showToast('Please fill in all fields', 'error');
        return;
    }
    
    const response = await API.post('/templates', { name, body });
    
    if (response.success) {
        hideModal('template-modal');
        document.getElementById('template-name').value = '';
        document.getElementById('template-body').value = '';
        await loadTemplates();
        showToast('Template created');
    } else {
        showToast(response.error || 'Failed to create template', 'error');
    }
}

// ============ Event Listeners ============
function initEventListeners() {
    // Modal close buttons
    document.querySelectorAll('.modal-close, .modal-cancel').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.modal').classList.remove('active');
        });
    });
    
    // Close modal on backdrop click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.classList.remove('active');
        });
    });
    
    // Contact search
    let searchTimeout;
    document.getElementById('contact-search').addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => loadContacts(e.target.value), 300);
    });
    
    // Mobile only filter
    const mobileOnlyFilter = document.getElementById('mobile-only-filter');
    if (mobileOnlyFilter) {
        mobileOnlyFilter.addEventListener('change', () => loadContacts());
    }
    
    // Send reply
    document.getElementById('send-reply').addEventListener('click', sendReply);
    document.getElementById('reply-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendReply();
        }
    });
    
    // Recipient type toggle
    document.querySelectorAll('input[name="recipient-type"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            document.getElementById('single-number-group').style.display = 
                e.target.value === 'single' ? 'block' : 'none';
            document.getElementById('selected-contacts-group').style.display = 
                e.target.value === 'selected' ? 'block' : 'none';
        });
    });
    
    // Initialize visibility based on default selection
    const defaultType = document.querySelector('input[name="recipient-type"]:checked')?.value || 'selected';
    document.getElementById('single-number-group').style.display = defaultType === 'single' ? 'block' : 'none';
    document.getElementById('selected-contacts-group').style.display = defaultType === 'selected' ? 'block' : 'none';
    
    // Schedule toggle
    document.getElementById('schedule-message').addEventListener('change', (e) => {
        document.getElementById('schedule-group').style.display = 
            e.target.checked ? 'block' : 'none';
        document.getElementById('send-message-btn').innerHTML = e.target.checked
            ? '<i class="fas fa-clock"></i> Schedule'
            : '<i class="fas fa-paper-plane"></i> Send Now';
    });
    
    // Message body character count
    document.getElementById('message-body').addEventListener('input', updateCharCount);
    
    // Send message
    document.getElementById('send-message-btn').addEventListener('click', sendMessage);
    
    // Template selection
    document.getElementById('message-template').addEventListener('change', (e) => {
        const template = state.templates.find(t => t.id === parseInt(e.target.value));
        if (template) {
            document.getElementById('message-body').value = template.body;
            updateCharCount();
        }
    });
    
    // Add template button
    document.getElementById('add-template-btn').addEventListener('click', () => {
        document.getElementById('template-form').reset();
        showModal('template-modal');
    });
    
    // Save template
    document.getElementById('save-template-btn').addEventListener('click', saveTemplate);
    
    // Select all contacts
    document.getElementById('select-all-contacts').addEventListener('change', (e) => {
        document.querySelectorAll('.contact-select').forEach(cb => {
            cb.checked = e.target.checked;
        });
    });
    
    // ============ Contact Management ============
    
    // Contact tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            state.contactsTab = btn.dataset.tab;
            updateContactsTabs();
            loadContacts();
        });
    });
    
    // Add contact button
    document.getElementById('add-contact-btn').addEventListener('click', openAddContactModal);
    
    // Save contact button
    document.getElementById('save-contact-btn').addEventListener('click', saveContact);
    
    // CSV upload button
    document.getElementById('upload-csv-btn').addEventListener('click', () => {
        document.getElementById('csv-file').value = '';
        document.getElementById('csv-preview').style.display = 'none';
        document.getElementById('upload-csv-submit').disabled = true;
        csvFileData = null;
        showModal('csv-modal');
    });
    
    // CSV file selection
    document.getElementById('csv-file').addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            previewCSV(e.target.files[0]);
        }
    });
    
    // CSV upload submit
    document.getElementById('upload-csv-submit').addEventListener('click', uploadCSV);
}

// ============ Initialize ============
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initEventListeners();
    loadDashboard();
});
