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

// ============ Skeleton Loaders ============
function showStatsSkeleton() {
    const statIds = ['stat-contacts', 'stat-total', 'stat-sent', 'stat-received'];
    statIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.innerHTML = '<div class="skeleton" style="height: 28px; width: 50px; display: inline-block;"></div>';
        }
    });
}

function showMessagesSkeleton() {
    const container = document.getElementById('recent-messages');
    if (!container) return;
    
    container.innerHTML = Array(5).fill(0).map(() => `
        <div class="skeleton-message-item">
            <div class="skeleton-message-info">
                <div class="skeleton skeleton-message-phone"></div>
                <div class="skeleton skeleton-message-body"></div>
            </div>
            <div class="skeleton-message-meta">
                <div class="skeleton skeleton-message-time"></div>
                <div class="skeleton skeleton-message-status"></div>
            </div>
        </div>
    `).join('');
}

function showConversationsSkeleton() {
    const container = document.getElementById('conversation-list');
    if (!container) return;
    
    container.innerHTML = Array(8).fill(0).map(() => `
        <div class="skeleton-conversation-item">
            <div class="skeleton-conversation-header">
                <div class="skeleton skeleton-conversation-name"></div>
                <div class="skeleton skeleton-conversation-time"></div>
            </div>
            <div class="skeleton skeleton-conversation-preview"></div>
        </div>
    `).join('');
}

function showContactsSkeleton() {
    const tbody = document.getElementById('contacts-table-body');
    if (!tbody) return;
    
    tbody.innerHTML = Array(10).fill(0).map(() => `
        <tr class="skeleton-table-row">
            <td><div class="skeleton skeleton-table-cell" style="width: 20px; height: 20px;"></div></td>
            <td><div class="skeleton skeleton-table-cell" style="width: 120px;"></div></td>
            <td><div class="skeleton skeleton-table-cell" style="width: 100px;"></div></td>
            <td><div class="skeleton skeleton-table-cell" style="width: 140px;"></div></td>
            <td><div class="skeleton skeleton-table-cell" style="width: 80px;"></div></td>
            <td><div class="skeleton skeleton-table-cell" style="width: 60px;"></div></td>
            <td><div class="skeleton skeleton-table-cell" style="width: 80px;"></div></td>
        </tr>
    `).join('');
}

function showTemplatesSkeleton() {
    const container = document.getElementById('templates-list');
    if (!container) return;
    
    container.innerHTML = Array(4).fill(0).map(() => `
        <div class="skeleton-template-card">
            <div class="skeleton skeleton-template-title"></div>
            <div class="skeleton skeleton-template-body long"></div>
            <div class="skeleton skeleton-template-body medium"></div>
            <div class="skeleton-template-actions">
                <div class="skeleton skeleton-template-btn"></div>
                <div class="skeleton skeleton-template-btn"></div>
            </div>
        </div>
    `).join('');
}

function showScheduledSkeleton() {
    const container = document.getElementById('scheduled-list');
    if (!container) return;
    
    container.innerHTML = Array(3).fill(0).map(() => `
        <div class="skeleton-scheduled-item">
            <div class="skeleton-scheduled-info">
                <div class="skeleton skeleton-scheduled-title"></div>
                <div class="skeleton skeleton-scheduled-detail"></div>
                <div class="skeleton skeleton-scheduled-detail" style="width: 100px;"></div>
            </div>
            <div class="skeleton-scheduled-actions">
                <div class="skeleton skeleton-scheduled-btn"></div>
                <div class="skeleton skeleton-scheduled-btn"></div>
            </div>
        </div>
    `).join('');
}

// ============ Dashboard ============
async function loadDashboard() {
    // Show skeletons immediately
    showStatsSkeleton();
    showMessagesSkeleton();
    
    // Load stats and messages in parallel, render each as it arrives
    API.get('/stats').then(statsResponse => {
        if (statsResponse.success) {
            const stats = statsResponse.stats;
            document.getElementById('stat-contacts').textContent = stats.total_contacts;
            document.getElementById('stat-total').textContent = stats.total_messages;
            document.getElementById('stat-sent').textContent = stats.sent_messages;
            document.getElementById('stat-received').textContent = stats.received_messages;
        }
    });
    
    API.get('/messages?limit=10').then(messagesResponse => {
        if (messagesResponse.success) {
            renderRecentMessages(messagesResponse.messages);
        }
    });
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
    // Show skeleton immediately
    showConversationsSkeleton();
    
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
    
    // Update header - show name prominently with phone smaller, add "Add Contact" if no name
    let headerHtml = name 
        ? `<strong>${name}</strong><small style="color: var(--text-secondary); margin-left: 12px; font-weight: normal;">${phone}</small>`
        : `<strong>${phone}</strong>
           <button class="btn btn-sm btn-secondary" id="add-contact-from-conv" style="margin-left: 12px;" title="Add to Contacts">
               <i class="fas fa-user-plus"></i> Add Contact
           </button>`;
    
    document.getElementById('conversation-header').innerHTML = headerHtml;
    
    // Add click handler for "Add Contact" button if present
    const addBtn = document.getElementById('add-contact-from-conv');
    if (addBtn) {
        addBtn.addEventListener('click', () => {
            openAddContactModalWithPhone(phone);
        });
    }
    
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
    // Show skeleton immediately
    showContactsSkeleton();
    
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
    const isManual = state.contactsTab === 'manual';
    
    if (state.contacts.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="empty-state">
                    <i class="fas fa-address-book"></i>
                    <p>No contacts found</p>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = state.contacts.map(contact => {
        const phone = contact.phone_number || contact.phone;
        const actionButtons = isManual ? `
            <button class="btn btn-sm btn-secondary edit-contact" data-id="${contact.id}" title="Edit">
                <i class="fas fa-edit"></i>
            </button>
            <button class="btn btn-sm btn-danger delete-contact" data-id="${contact.id}" title="Delete">
                <i class="fas fa-trash"></i>
            </button>
        ` : `
            <button class="btn btn-sm btn-secondary lead-notes-btn" data-phone="${phone}" data-name="${contact.name || ''}" data-company="${contact.company || ''}" title="Add Notes">
                <i class="fas fa-sticky-note"></i>
            </button>
        `;
        
        return `
            <tr>
                <td><input type="checkbox" class="contact-select" data-phone="${phone}"></td>
                <td>${contact.name || '-'}</td>
                <td>${phone}</td>
                <td>${contact.company || '-'}</td>
                <td>${contact.role || '-'}</td>
                <td><span class="badge badge-${contact.source}">${contact.source || 'permit'}</span></td>
                <td>${actionButtons}</td>
            </tr>
        `;
    }).join('');
    
    // Add event handlers
    if (isManual) {
        tbody.querySelectorAll('.edit-contact').forEach(btn => {
            btn.addEventListener('click', () => editContact(parseInt(btn.dataset.id)));
        });
        tbody.querySelectorAll('.delete-contact').forEach(btn => {
            btn.addEventListener('click', () => deleteContact(parseInt(btn.dataset.id)));
        });
    } else {
        tbody.querySelectorAll('.lead-notes-btn').forEach(btn => {
            btn.addEventListener('click', () => openLeadNotesModal(btn.dataset.phone, btn.dataset.name, btn.dataset.company));
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
        
        // Reload conversations to show new contact name
        if (state.currentConversation) {
            await loadConversations();
            await loadConversation(state.currentConversation);
        }
        
        // Reload manual contacts if on that tab
        if (state.contactsTab === 'manual') {
            await loadManualContacts();
        }
    } else {
        showToast(response.error || 'Failed to save contact', 'error');
    }
}

function openAddContactModalWithPhone(phone) {
    document.getElementById('contact-modal-title').textContent = 'Add Contact';
    document.getElementById('contact-form').reset();
    document.getElementById('contact-edit-id').value = '';
    document.getElementById('contact-phone').value = phone;
    showModal('contact-modal');
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

// ============ Lead Notes (for Leads DB contacts) ============

async function openLeadNotesModal(phone, name, company) {
    document.getElementById('lead-notes-name').textContent = name || 'Unknown Contact';
    document.getElementById('lead-notes-phone').textContent = phone;
    document.getElementById('lead-notes-company').textContent = company || '';
    document.getElementById('lead-notes-phone-input').value = phone;
    
    // Load existing notes if any
    const response = await API.get(`/contacts/notes/${encodeURIComponent(phone)}`);
    if (response.success && response.note) {
        document.getElementById('lead-notes-textarea').value = response.note.notes || '';
    } else {
        document.getElementById('lead-notes-textarea').value = '';
    }
    
    showModal('lead-notes-modal');
}

async function saveLeadNotes() {
    const phone = document.getElementById('lead-notes-phone-input').value;
    const notes = document.getElementById('lead-notes-textarea').value.trim();
    
    const response = await API.post('/contacts/notes', { phone, notes });
    
    if (response.success) {
        hideModal('lead-notes-modal');
        showToast('Notes saved');
    } else {
        showToast(response.error || 'Failed to save notes', 'error');
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

// Store all contacts for the picker
let allComposeContacts = [];
let selectedContactPhones = new Set();

async function loadComposeView() {
    // Load contacts for selector (mobile only for SMS)
    const response = await API.get('/contacts?mobile_only=true&limit=500');
    allComposeContacts = response.success ? response.contacts : [];
    
    // Load templates
    await loadTemplates();
    
    // Populate template dropdown
    const templateSelect = document.getElementById('message-template');
    templateSelect.innerHTML = '<option value="">-- Select Template --</option>' +
        state.templates.map(t => `<option value="${t.id}">${t.name}</option>`).join('');
    
    // Populate role filter
    populateRoleFilter();
    
    // Render chips
    renderSelectedChips();
    updateSelectedCount();
}

function populateRoleFilter() {
    const roles = [...new Set(allComposeContacts.map(c => c.role).filter(Boolean))];
    const select = document.getElementById('contact-picker-role-filter');
    if (select) {
        select.innerHTML = '<option value="">All Roles</option>' +
            roles.map(r => `<option value="${r}">${r}</option>`).join('');
    }
}

function openContactPicker() {
    renderContactPickerList();
    showModal('contact-picker-modal');
}

function renderContactPickerList(searchTerm = '', roleFilter = '') {
    const container = document.getElementById('contact-picker-list');
    if (!container) return;
    
    // Filter contacts
    let filtered = allComposeContacts;
    
    if (searchTerm) {
        const term = searchTerm.toLowerCase();
        filtered = filtered.filter(c => 
            (c.name && c.name.toLowerCase().includes(term)) ||
            (c.phone && c.phone.includes(term)) ||
            (c.company && c.company.toLowerCase().includes(term))
        );
    }
    
    if (roleFilter) {
        filtered = filtered.filter(c => c.role === roleFilter);
    }
    
    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="contact-picker-empty">
                <i class="fas fa-search"></i>
                <p>No contacts found</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = filtered.map(c => {
        const isSelected = selectedContactPhones.has(c.phone);
        return `
            <div class="contact-picker-item ${isSelected ? 'selected' : ''}" data-phone="${c.phone}">
                <input type="checkbox" ${isSelected ? 'checked' : ''}>
                <div class="contact-picker-item-info">
                    <div class="contact-picker-item-name">${c.name || 'Unknown'}</div>
                    <div class="contact-picker-item-details">
                        <span class="contact-picker-item-phone">${c.phone}</span>
                        ${c.company ? `<span>${c.company}</span>` : ''}
                        ${c.role ? `<span class="contact-picker-item-role">${c.role}</span>` : ''}
                    </div>
                </div>
            </div>
        `;
    }).join('');
    
    // Add click handlers
    container.querySelectorAll('.contact-picker-item').forEach(item => {
        item.addEventListener('click', (e) => {
            const phone = item.dataset.phone;
            const checkbox = item.querySelector('input[type="checkbox"]');
            
            if (selectedContactPhones.has(phone)) {
                selectedContactPhones.delete(phone);
                item.classList.remove('selected');
                checkbox.checked = false;
            } else {
                if (selectedContactPhones.size >= MAX_RECIPIENTS) {
                    showToast(`Maximum ${MAX_RECIPIENTS} recipients allowed`, 'error');
                    return;
                }
                selectedContactPhones.add(phone);
                item.classList.add('selected');
                checkbox.checked = true;
            }
            
            updatePickerCount();
        });
    });
    
    updatePickerCount();
}

function updatePickerCount() {
    const countEl = document.getElementById('contact-picker-count');
    if (countEl) {
        const count = selectedContactPhones.size;
        countEl.textContent = `${count} contact${count !== 1 ? 's' : ''} selected`;
        countEl.style.color = count > MAX_RECIPIENTS ? '#dc2626' : 'var(--text-secondary)';
    }
}

function confirmContactSelection() {
    renderSelectedChips();
    updateSelectedCount();
    hideModal('contact-picker-modal');
}

function renderSelectedChips() {
    const container = document.getElementById('selected-contacts-chips');
    if (!container) return;
    
    if (selectedContactPhones.size === 0) {
        container.innerHTML = '<span class="no-contacts-hint">No contacts selected</span>';
        return;
    }
    
    // Get contact info for selected phones
    const selectedContacts = allComposeContacts.filter(c => selectedContactPhones.has(c.phone));
    
    container.innerHTML = selectedContacts.map(c => `
        <div class="contact-chip" data-phone="${c.phone}">
            <span>${c.name || c.phone}</span>
            <span class="chip-remove" onclick="removeContactChip('${c.phone}')">
                <i class="fas fa-times"></i>
            </span>
        </div>
    `).join('');
}

function removeContactChip(phone) {
    selectedContactPhones.delete(phone);
    renderSelectedChips();
    updateSelectedCount();
}

function selectAllVisibleContacts() {
    const items = document.querySelectorAll('#contact-picker-list .contact-picker-item');
    items.forEach(item => {
        const phone = item.dataset.phone;
        if (!selectedContactPhones.has(phone) && selectedContactPhones.size < MAX_RECIPIENTS) {
            selectedContactPhones.add(phone);
            item.classList.add('selected');
            item.querySelector('input[type="checkbox"]').checked = true;
        }
    });
    updatePickerCount();
}

function clearAllContacts() {
    selectedContactPhones.clear();
    document.querySelectorAll('#contact-picker-list .contact-picker-item').forEach(item => {
        item.classList.remove('selected');
        item.querySelector('input[type="checkbox"]').checked = false;
    });
    updatePickerCount();
}

function updateSelectedCount() {
    const countEl = document.getElementById('selected-count');
    if (countEl) {
        const count = selectedContactPhones.size;
        countEl.textContent = `(${count} selected, max ${MAX_RECIPIENTS})`;
        countEl.style.color = count > MAX_RECIPIENTS ? '#dc2626' : 'var(--text-secondary)';
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
        phoneNumbers = Array.from(selectedContactPhones);
        
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
        
        // Get recurring options
        const isRecurring = document.getElementById('is-recurring').checked;
        const recurrenceType = document.getElementById('recurrence-type').value;
        const recurrenceEnd = document.getElementById('recurrence-end').value;
        
        // Get selected days for weekly
        let recurrenceDays = null;
        if (isRecurring && recurrenceType === 'weekly') {
            const selectedDays = Array.from(
                document.querySelectorAll('#weekly-days-group input:checked')
            ).map(cb => cb.value);
            
            if (selectedDays.length === 0) {
                showToast('Please select at least one day for weekly recurrence', 'error');
                return;
            }
            recurrenceDays = selectedDays.join(',');
        }
        
        // Build confirmation message
        let confirmMsg = `Schedule message to ${phoneNumbers.length} recipient(s)?\\n\\nFirst send: ${new Date(datetime).toLocaleString()}`;
        if (isRecurring) {
            let recurrenceLabel;
            if (recurrenceType === 'daily') {
                recurrenceLabel = 'every day';
            } else if (recurrenceType === 'weekly') {
                recurrenceLabel = `every ${recurrenceDays.split(',').join(', ')}`;
            } else if (recurrenceType === 'monthly') {
                recurrenceLabel = 'every month (same day)';
            }
            confirmMsg += `\\nRepeats: ${recurrenceLabel}`;
            if (recurrenceEnd) {
                confirmMsg += `\\nUntil: ${new Date(recurrenceEnd).toLocaleDateString()}`;
            }
        }
        
        const confirmed = confirm(confirmMsg);
        if (!confirmed) return;
        
        const scheduleData = {
            name,
            body,
            scheduled_at: new Date(datetime).toISOString(),
            phone_numbers: phoneNumbers,
            is_recurring: isRecurring,
            recurrence_type: isRecurring ? recurrenceType : null,
            recurrence_days: recurrenceDays,
            recurrence_end_date: recurrenceEnd ? new Date(recurrenceEnd + 'T23:59:59').toISOString() : null
        };
        
        const response = await API.post('/scheduled', scheduleData);
        
        if (response.success) {
            const recurText = isRecurring ? ' (recurring)' : '';
            showToast(`Message scheduled to ${phoneNumbers.length} recipients${recurText}`);
            document.getElementById('message-body').value = '';
            document.getElementById('schedule-name').value = '';
            document.getElementById('schedule-datetime').value = '';
            document.getElementById('is-recurring').checked = false;
            document.getElementById('recurring-options').style.display = 'none';
            document.querySelectorAll('#weekly-days-group input').forEach(cb => cb.checked = false);
            document.getElementById('recurrence-end').value = '';
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
    // Show skeleton immediately
    showScheduledSkeleton();
    
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
    
    container.innerHTML = scheduled.map(item => {
        // Build recurrence info
        let recurrenceInfo = '';
        if (item.is_recurring) {
            const typeLabel = {
                'daily': 'Daily',
                'weekly': `Weekly (${item.recurrence_days || 'every day'})`,
                'monthly': 'Monthly'
            }[item.recurrence_type] || item.recurrence_type;
            
            recurrenceInfo = `
                <p><i class="fas fa-redo"></i> ${typeLabel}${item.send_count ? ` • Sent ${item.send_count} times` : ''}</p>
            `;
            
            if (item.recurrence_end_date) {
                recurrenceInfo += `<p style="font-size: 0.85em; color: var(--text-muted);"><i class="fas fa-stop-circle"></i> Ends ${new Date(item.recurrence_end_date).toLocaleDateString()}</p>`;
            }
        }
        
        // Build action buttons based on status
        let actionButtons = '';
        if (item.status === 'pending') {
            if (item.is_recurring) {
                actionButtons = `
                    <button class="btn btn-secondary btn-sm pause-scheduled" data-id="${item.id}" title="Pause">
                        <i class="fas fa-pause"></i>
                    </button>
                    <button class="btn btn-danger btn-sm cancel-scheduled" data-id="${item.id}" title="Cancel">
                        <i class="fas fa-times"></i>
                    </button>
                `;
            } else {
                actionButtons = `
                    <button class="btn btn-danger btn-sm cancel-scheduled" data-id="${item.id}">
                        <i class="fas fa-times"></i> Cancel
                    </button>
                `;
            }
        } else if (item.status === 'paused') {
            actionButtons = `
                <button class="btn btn-primary btn-sm resume-scheduled" data-id="${item.id}" title="Resume">
                    <i class="fas fa-play"></i> Resume
                </button>
                <button class="btn btn-danger btn-sm cancel-scheduled" data-id="${item.id}" title="Cancel">
                    <i class="fas fa-times"></i>
                </button>
            `;
        }
        
        return `
            <div class="scheduled-item">
                <div class="scheduled-info">
                    <h4>${item.name} ${item.is_recurring ? '<i class="fas fa-redo" style="color: var(--primary-color); font-size: 0.8em;" title="Recurring"></i>' : ''}</h4>
                    <p><i class="fas fa-calendar"></i> ${item.status === 'paused' ? 'Paused' : 'Next:'} ${new Date(item.scheduled_at).toLocaleString()}</p>
                    <p><i class="fas fa-users"></i> ${item.total_recipients} recipients</p>
                    ${recurrenceInfo}
                    <p>${item.body.substring(0, 100)}${item.body.length > 100 ? '...' : ''}</p>
                    <span class="scheduled-status ${item.status}">${item.status}</span>
                </div>
                <div style="display: flex; gap: 8px;">
                    ${actionButtons}
                </div>
            </div>
        `;
    }).join('');
    
    // Add cancel handlers
    container.querySelectorAll('.cancel-scheduled').forEach(btn => {
        btn.addEventListener('click', async () => {
            if (!confirm('Are you sure you want to cancel this scheduled message?')) return;
            const response = await API.delete(`/scheduled/${btn.dataset.id}`);
            if (response.success) {
                await loadScheduled();
                showToast('Scheduled message cancelled');
            }
        });
    });
    
    // Add pause handlers
    container.querySelectorAll('.pause-scheduled').forEach(btn => {
        btn.addEventListener('click', async () => {
            const response = await API.post(`/scheduled/${btn.dataset.id}/pause`);
            if (response.success) {
                await loadScheduled();
                showToast('Schedule paused');
            } else {
                showToast(response.error || 'Failed to pause', 'error');
            }
        });
    });
    
    // Add resume handlers
    container.querySelectorAll('.resume-scheduled').forEach(btn => {
        btn.addEventListener('click', async () => {
            const response = await API.post(`/scheduled/${btn.dataset.id}/resume`);
            if (response.success) {
                await loadScheduled();
                showToast('Schedule resumed');
            } else {
                showToast(response.error || 'Failed to resume', 'error');
            }
        });
    });
}

// ============ Templates ============
const TEMPLATE_VARIABLES = {
    '{name}': (contact) => contact?.name || '',
    '{company}': (contact) => contact?.company || '',
    '{role}': (contact) => contact?.role || '',
    '{phone}': (contact) => contact?.phone || contact?.phone_number || '',
    '{date}': () => new Date().toLocaleDateString(),
    '{time}': () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
};

function highlightVariables(text) {
    // Highlight variables in template preview
    return text.replace(/\{(\w+)\}/g, '<span class="template-var">{$1}</span>');
}

function fillTemplateVariables(template, contact) {
    let result = template;
    for (const [variable, getter] of Object.entries(TEMPLATE_VARIABLES)) {
        const value = getter(contact);
        result = result.replace(new RegExp(variable.replace(/[{}]/g, '\\$&'), 'g'), value);
    }
    return result;
}

function hasUnfilledVariables(text) {
    // Check if there are any unfilled variables (empty replacements)
    return /\{(\w+)\}/.test(text) || text.includes('  ') || text.startsWith(' ');
}

async function loadTemplates() {
    // Show skeleton immediately
    showTemplatesSkeleton();
    
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
    
    container.innerHTML = state.templates.map(template => {
        // Highlight variables in preview
        const previewBody = highlightVariables(template.body);
        // Detect which variables are used
        const usedVars = (template.body.match(/\{(\w+)\}/g) || []).join(' ');
        
        return `
            <div class="template-card">
                <h4>${template.name}</h4>
                <p class="template-preview">${previewBody}</p>
                ${usedVars ? `<p style="margin-top: 8px; font-size: 0.8rem; color: var(--text-muted);"><i class="fas fa-magic"></i> Uses: ${usedVars}</p>` : ''}
                <div class="template-actions">
                    <button class="btn btn-sm btn-primary use-template" data-id="${template.id}" data-body="${encodeURIComponent(template.body)}">
                        <i class="fas fa-edit"></i> Use
                    </button>
                    <button class="btn btn-sm btn-danger delete-template" data-id="${template.id}">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
    
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
    
    // Contact Picker
    document.getElementById('open-contact-picker-btn')?.addEventListener('click', openContactPicker);
    document.getElementById('contact-picker-confirm')?.addEventListener('click', confirmContactSelection);
    document.getElementById('contact-picker-select-all')?.addEventListener('click', selectAllVisibleContacts);
    document.getElementById('contact-picker-clear-all')?.addEventListener('click', clearAllContacts);
    
    // Contact Picker Search
    document.getElementById('contact-picker-search')?.addEventListener('input', (e) => {
        const roleFilter = document.getElementById('contact-picker-role-filter')?.value || '';
        renderContactPickerList(e.target.value, roleFilter);
    });
    
    // Contact Picker Role Filter
    document.getElementById('contact-picker-role-filter')?.addEventListener('change', (e) => {
        const searchTerm = document.getElementById('contact-picker-search')?.value || '';
        renderContactPickerList(searchTerm, e.target.value);
    });
    
    // Recurring toggle
    document.getElementById('is-recurring').addEventListener('change', (e) => {
        document.getElementById('recurring-options').style.display = 
            e.target.checked ? 'block' : 'none';
    });
    
    // Recurrence type toggle (show/hide weekly days)
    document.getElementById('recurrence-type').addEventListener('change', (e) => {
        document.getElementById('weekly-days-group').style.display = 
            e.target.value === 'weekly' ? 'block' : 'none';
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
    
    // Variable insert buttons in template modal
    document.querySelectorAll('.insert-var').forEach(btn => {
        btn.addEventListener('click', () => {
            const textarea = document.getElementById('template-body');
            const variable = btn.dataset.var;
            const start = textarea.selectionStart;
            const end = textarea.selectionEnd;
            const text = textarea.value;
            textarea.value = text.substring(0, start) + variable + text.substring(end);
            textarea.focus();
            textarea.setSelectionRange(start + variable.length, start + variable.length);
        });
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
    
    // Save lead notes button
    document.getElementById('save-lead-notes-btn').addEventListener('click', saveLeadNotes);
    
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
