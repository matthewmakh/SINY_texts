// ============ Auth State ============
let currentUser = null;

// ============ Auth Functions ============
async function checkAuth() {
    try {
        const result = await API.get('/auth/me');
        if (result.success && result.user) {
            currentUser = result.user;
            showApp();
            updateUserDisplay();
            return true;
        }
    } catch (e) {
        console.log('Not authenticated');
    }
    showLogin();
    return false;
}

function showLogin() {
    document.getElementById('login-screen').classList.add('active');
    document.querySelector('.app-container').style.display = 'none';
}

function showApp() {
    document.getElementById('login-screen').classList.remove('active');
    document.querySelector('.app-container').style.display = 'flex';
    
    // Show admin-only elements if admin
    if (currentUser && currentUser.role === 'admin') {
        document.querySelectorAll('.admin-only').forEach(el => el.style.display = '');
    }
}

function updateUserDisplay() {
    if (currentUser) {
        document.getElementById('user-display-name').textContent = currentUser.name;
        document.getElementById('user-display-role').textContent = currentUser.role;
    }
}

async function handleLogin(e) {
    e.preventDefault();
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');
    
    try {
        const result = await API.post('/auth/login', { email, password });
        if (result.success) {
            currentUser = result.user;
            showApp();
            updateUserDisplay();
            loadDashboard();
            errorEl.style.display = 'none';
        } else {
            errorEl.textContent = result.error || 'Login failed';
            errorEl.style.display = 'block';
        }
    } catch (e) {
        errorEl.textContent = 'Connection error';
        errorEl.style.display = 'block';
    }
}

async function handleLogout() {
    await API.post('/auth/logout', {});
    currentUser = null;
    showLogin();
    document.getElementById('login-email').value = '';
    document.getElementById('login-password').value = '';
}

async function handleChangePassword(e) {
    e.preventDefault();
    const currentPassword = document.getElementById('current-password').value;
    const newPassword = document.getElementById('new-password').value;
    const confirmPassword = document.getElementById('confirm-password').value;
    
    if (newPassword !== confirmPassword) {
        showToast('Passwords do not match', 'error');
        return;
    }
    
    if (newPassword.length < 8) {
        showToast('Password must be at least 8 characters', 'error');
        return;
    }
    
    const result = await API.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword
    });
    
    if (result.success) {
        showToast('Password changed successfully');
        hideModal('password-modal');
        document.getElementById('password-form').reset();
    } else {
        showToast(result.error || 'Failed to change password', 'error');
    }
}

// ============ User Management Functions ============
async function loadUsers() {
    const result = await API.get('/users?include_inactive=true');
    if (result.success) {
        renderUsers(result.users);
    }
}

function renderUsers(users) {
    const tbody = document.getElementById('users-list');
    tbody.innerHTML = users.map(user => `
        <tr>
            <td>
                <div class="user-cell">
                    <div class="user-avatar-small">${user.name.charAt(0).toUpperCase()}</div>
                    <div class="user-cell-info">
                        <span class="user-cell-name">${user.name}</span>
                        <span class="user-cell-email">${user.email}</span>
                    </div>
                </div>
            </td>
            <td><span class="role-badge role-${user.role}">${user.role}</span></td>
            <td><span class="user-status ${user.is_active ? 'active' : 'inactive'}">${user.is_active ? 'Active' : 'Inactive'}</span></td>
            <td>${user.last_login ? formatDate(user.last_login) : 'Never'}</td>
            <td class="actions-cell">
                <button class="btn-icon" onclick="editUser(${user.id})" title="Edit">
                    <i class="fas fa-edit"></i>
                </button>
                ${user.id !== currentUser.id ? `
                    <button class="btn-icon danger" onclick="deleteUserConfirm(${user.id})" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                ` : ''}
            </td>
        </tr>
    `).join('');
}

let usersCache = [];

async function editUser(userId) {
    if (!usersCache.length) {
        const result = await API.get('/users?include_inactive=true');
        if (result.success) usersCache = result.users;
    }
    
    const user = usersCache.find(u => u.id === userId);
    if (!user) return;
    
    document.getElementById('user-modal-title').textContent = 'Edit User';
    document.getElementById('user-edit-id').value = user.id;
    document.getElementById('user-name').value = user.name;
    document.getElementById('user-email').value = user.email;
    document.getElementById('user-email').disabled = true;
    document.getElementById('user-password').value = '';
    document.getElementById('user-password-group').style.display = 'none';
    document.getElementById('user-role').value = user.role;
    document.getElementById('user-active').checked = user.is_active;
    
    showModal('user-modal');
}

function showAddUserModal() {
    document.getElementById('user-modal-title').textContent = 'Add User';
    document.getElementById('user-form').reset();
    document.getElementById('user-edit-id').value = '';
    document.getElementById('user-email').disabled = false;
    document.getElementById('user-password-group').style.display = 'block';
    document.getElementById('user-active').checked = true;
    showModal('user-modal');
}

async function saveUser() {
    const userId = document.getElementById('user-edit-id').value;
    const data = {
        name: document.getElementById('user-name').value,
        role: document.getElementById('user-role').value,
        is_active: document.getElementById('user-active').checked
    };
    
    if (!userId) {
        // Creating new user
        data.email = document.getElementById('user-email').value;
        data.password = document.getElementById('user-password').value;
        
        if (!data.password || data.password.length < 8) {
            showToast('Password must be at least 8 characters', 'error');
            return;
        }
    }
    
    let result;
    if (userId) {
        result = await API.put(`/users/${userId}`, data);
    } else {
        result = await API.post('/users', data);
    }
    
    if (result.success) {
        showToast(userId ? 'User updated' : 'User created');
        hideModal('user-modal');
        usersCache = [];
        loadUsers();
    } else {
        showToast(result.error || 'Failed to save user', 'error');
    }
}

async function deleteUserConfirm(userId) {
    if (!confirm('Are you sure you want to delete this user?')) return;
    
    const result = await API.delete(`/users/${userId}`);
    if (result.success) {
        showToast('User deleted');
        usersCache = [];
        loadUsers();
    } else {
        showToast(result.error || 'Failed to delete user', 'error');
    }
}

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
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

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
        case 'campaigns':
            await loadCampaigns();
            break;
        case 'scheduled':
            await loadScheduled();
            break;
        case 'templates':
            await loadTemplates();
            break;
        case 'users':
            await loadUsers();
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

function showContactPickerSkeleton() {
    const container = document.getElementById('contact-picker-list');
    const countDisplay = document.getElementById('contact-picker-filtered-count');
    if (!container) return;
    
    // Show loading in count display
    if (countDisplay) {
        countDisplay.innerHTML = '<i class="fas fa-spinner fa-spin"></i><span>Loading contacts...</span>';
    }
    
    // Show skeleton items
    container.innerHTML = Array(6).fill(0).map(() => `
        <div class="skeleton-picker-item">
            <div class="skeleton skeleton-picker-checkbox"></div>
            <div class="skeleton-picker-info">
                <div class="skeleton skeleton-picker-name"></div>
                <div class="skeleton-picker-details">
                    <div class="skeleton skeleton-picker-phone"></div>
                    <div class="skeleton skeleton-picker-role"></div>
                </div>
            </div>
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
let contactsLoading = false;
let contactPickerPage = 1;
const CONTACTS_PER_PAGE = 500;

async function loadComposeView() {
    // Show skeleton in picker if it's open
    contactsLoading = true;
    contactPickerPage = 1;
    
    // Load contacts for selector (mobile only for SMS) - no limit to get all
    const response = await API.get('/contacts?mobile_only=true&limit=100000');
    allComposeContacts = response.success ? response.contacts : [];
    contactsLoading = false;
    
    // If contact picker is open, refresh it now that contacts are loaded
    const pickerModal = document.getElementById('contact-picker-modal');
    if (pickerModal && pickerModal.classList.contains('active')) {
        renderContactPickerList();
    }
    
    // Load templates
    await loadTemplates();
    
    // Populate template dropdown
    const templateSelect = document.getElementById('message-template');
    templateSelect.innerHTML = '<option value="">-- Select Template --</option>' +
        state.templates.map(t => `<option value="${t.id}">${t.name}</option>`).join('');
    
    // Populate role filter
    populateRoleFilter();
    
    // Load filter options (neighborhoods, zip codes)
    loadFilterOptions();
    
    // Render chips
    renderSelectedChips();
    updateSelectedCount();
}

async function loadFilterOptions() {
    try {
        const response = await API.get('/contacts/filter-options');
        if (response.success) {
            // Populate neighborhoods
            const neighborhoodSelect = document.getElementById('contact-picker-neighborhood-filter');
            if (neighborhoodSelect && response.neighborhoods) {
                neighborhoodSelect.innerHTML = '<option value="">All Neighborhoods</option>' +
                    response.neighborhoods.map(n => `<option value="${n.value}">${n.label}</option>`).join('');
            }
            
            // Populate zip codes
            const zipSelect = document.getElementById('contact-picker-zip-filter');
            if (zipSelect && response.zip_codes) {
                zipSelect.innerHTML = '<option value="">All Zip Codes</option>' +
                    response.zip_codes.map(z => `<option value="${z.value}">${z.label}</option>`).join('');
            }
        }
    } catch (e) {
        console.error('Failed to load filter options:', e);
    }
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
    // Show skeleton if contacts are loading or not yet loaded
    if (contactsLoading || allComposeContacts.length === 0) {
        showContactPickerSkeleton();
    } else {
        renderContactPickerList();
    }
    showModal('contact-picker-modal');
}

function getAdvancedFilters() {
    return {
        neighborhood: document.getElementById('contact-picker-neighborhood-filter')?.value || '',
        zip_code: document.getElementById('contact-picker-zip-filter')?.value || '',
        job_type: document.getElementById('contact-picker-jobtype-filter')?.value || '',
        work_type: document.getElementById('contact-picker-worktype-filter')?.value || '',
        permit_type: document.getElementById('contact-picker-permittype-filter')?.value || '',
        permit_status: document.getElementById('contact-picker-status-filter')?.value || '',
        bldg_type: document.getElementById('contact-picker-bldgtype-filter')?.value || '',
        residential: document.getElementById('contact-picker-residential-filter')?.value || ''
    };
}

function hasAdvancedFilters() {
    const filters = getAdvancedFilters();
    return Object.values(filters).some(v => v !== '');
}

function renderContactPickerList(searchTerm = '', roleFilter = '', boroughFilter = '') {
    const container = document.getElementById('contact-picker-list');
    const countDisplay = document.getElementById('contact-picker-filtered-count');
    if (!container) return;
    
    // Get current filter values from UI if not passed
    if (arguments.length === 0) {
        searchTerm = document.getElementById('contact-picker-search')?.value || '';
        roleFilter = document.getElementById('contact-picker-role-filter')?.value || '';
        boroughFilter = document.getElementById('contact-picker-borough-filter')?.value || '';
    }
    
    // Get advanced filters
    const advFilters = getAdvancedFilters();
    
    // Filter contacts
    let filtered = allComposeContacts;
    
    if (searchTerm) {
        const term = searchTerm.toLowerCase();
        filtered = filtered.filter(c => 
            (c.name && c.name.toLowerCase().includes(term)) ||
            (c.phone_number && c.phone_number.includes(term)) ||
            (c.company && c.company.toLowerCase().includes(term))
        );
    }
    
    if (roleFilter) {
        filtered = filtered.filter(c => c.role === roleFilter);
    }
    
    if (boroughFilter) {
        filtered = filtered.filter(c => c.borough === boroughFilter);
    }
    
    // Apply advanced filters
    if (advFilters.neighborhood) {
        filtered = filtered.filter(c => c.neighborhood === advFilters.neighborhood);
    }
    if (advFilters.zip_code) {
        filtered = filtered.filter(c => c.zip_code === advFilters.zip_code);
    }
    if (advFilters.job_type) {
        filtered = filtered.filter(c => c.job_type === advFilters.job_type);
    }
    if (advFilters.work_type) {
        filtered = filtered.filter(c => c.work_type === advFilters.work_type);
    }
    if (advFilters.permit_type) {
        filtered = filtered.filter(c => c.permit_type === advFilters.permit_type);
    }
    if (advFilters.permit_status) {
        filtered = filtered.filter(c => c.permit_status === advFilters.permit_status);
    }
    if (advFilters.bldg_type) {
        filtered = filtered.filter(c => c.bldg_type === advFilters.bldg_type);
    }
    if (advFilters.residential) {
        filtered = filtered.filter(c => c.residential === advFilters.residential);
    }
    
    // Update filtered count display
    if (countDisplay) {
        const totalCount = allComposeContacts.length;
        const filteredCount = filtered.length;
        const hasFilters = searchTerm || roleFilter || boroughFilter || hasAdvancedFilters();
        if (!hasFilters) {
            countDisplay.innerHTML = `<i class="fas fa-users"></i><span><strong>${totalCount.toLocaleString()}</strong> contacts available</span>`;
        } else {
            countDisplay.innerHTML = `<i class="fas fa-filter"></i><span><strong>${filteredCount.toLocaleString()}</strong> of ${totalCount.toLocaleString()} contacts match filters</span>`;
        }
    }
    
    if (filtered.length === 0) {
        container.innerHTML = `
            <div class="contact-picker-empty">
                <i class="fas fa-search"></i>
                <p>No contacts found</p>
            </div>
        `;
        renderContactPickerPagination(0, 0);
        return;
    }
    
    // Pagination
    const totalPages = Math.ceil(filtered.length / CONTACTS_PER_PAGE);
    if (contactPickerPage > totalPages) contactPickerPage = 1;
    const startIdx = (contactPickerPage - 1) * CONTACTS_PER_PAGE;
    const endIdx = startIdx + CONTACTS_PER_PAGE;
    const pageContacts = filtered.slice(startIdx, endIdx);
    
    container.innerHTML = pageContacts.map(c => {
        const isSelected = selectedContactPhones.has(c.phone_number);
        
        // Smart name display: use name, fall back to company if name is NA/N/A/empty
        let displayName = c.name;
        const isNameEmpty = !displayName || displayName === 'NA' || displayName === 'N/A' || displayName === 'null' || displayName.trim() === '';
        if (isNameEmpty && c.company) {
            displayName = c.company;
        } else if (isNameEmpty) {
            displayName = 'Unknown';
        }
        
        // Show company only if different from display name
        const showCompany = c.company && c.company !== displayName && c.company !== 'N/A' && c.company !== 'None';
        
        return `
            <div class="contact-picker-item ${isSelected ? 'selected' : ''}" data-phone="${c.phone_number}">
                <input type="checkbox" ${isSelected ? 'checked' : ''}>
                <div class="contact-picker-item-info">
                    <div class="contact-picker-item-name">${displayName}</div>
                    <div class="contact-picker-item-details">
                        <span class="contact-picker-item-phone">${c.phone_number}</span>
                        ${showCompany ? `<span class="contact-picker-item-company">${c.company}</span>` : ''}
                        ${c.address ? `<span class="contact-picker-item-address">${c.address}</span>` : ''}
                    </div>
                    <div class="contact-picker-item-tags">
                        ${c.role ? `<span class="contact-picker-item-role">${c.role}</span>` : ''}
                        ${c.borough ? `<span class="contact-picker-item-borough">${c.borough}</span>` : ''}
                        ${c.source === 'manual' ? `<span class="contact-picker-item-manual">Manual</span>` : ''}
                    </div>
                </div>
            </div>
        `;
    }).join('');
    
    // Render pagination
    renderContactPickerPagination(filtered.length, totalPages);
    
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

function renderContactPickerPagination(totalContacts, totalPages) {
    let paginationContainer = document.getElementById('contact-picker-pagination');
    if (!paginationContainer) {
        // Create pagination container if doesn't exist
        const listContainer = document.getElementById('contact-picker-list');
        if (listContainer) {
            paginationContainer = document.createElement('div');
            paginationContainer.id = 'contact-picker-pagination';
            paginationContainer.className = 'contact-picker-pagination';
            listContainer.parentNode.insertBefore(paginationContainer, listContainer.nextSibling);
        }
    }
    
    if (!paginationContainer || totalPages <= 1) {
        if (paginationContainer) paginationContainer.innerHTML = '';
        return;
    }
    
    const startItem = (contactPickerPage - 1) * CONTACTS_PER_PAGE + 1;
    const endItem = Math.min(contactPickerPage * CONTACTS_PER_PAGE, totalContacts);
    
    paginationContainer.innerHTML = `
        <div class="pagination-info">
            Showing ${startItem.toLocaleString()}-${endItem.toLocaleString()} of ${totalContacts.toLocaleString()}
        </div>
        <div class="pagination-controls">
            <button class="btn btn-sm" ${contactPickerPage === 1 ? 'disabled' : ''} data-page="prev">
                <i class="fas fa-chevron-left"></i> Prev
            </button>
            <span class="pagination-current">Page ${contactPickerPage} of ${totalPages}</span>
            <button class="btn btn-sm" ${contactPickerPage === totalPages ? 'disabled' : ''} data-page="next">
                Next <i class="fas fa-chevron-right"></i>
            </button>
        </div>
    `;
    
    // Add pagination click handlers
    paginationContainer.querySelectorAll('button[data-page]').forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.disabled) return;
            if (btn.dataset.page === 'prev') {
                contactPickerPage--;
            } else if (btn.dataset.page === 'next') {
                contactPickerPage++;
            }
            applyContactPickerFilters(false); // Don't reset page
            // Scroll to top of list
            document.getElementById('contact-picker-list')?.scrollTo(0, 0);
        });
    });
}

function updatePickerCount() {
    const countEl = document.getElementById('contact-picker-count');
    if (countEl) {
        const count = selectedContactPhones.size;
        countEl.textContent = `${count} contact${count !== 1 ? 's' : ''} selected`;
        countEl.style.color = count > MAX_RECIPIENTS ? '#dc2626' : 'var(--text-secondary)';
    }
}

function applyContactPickerFilters(resetPage = true) {
    if (resetPage) contactPickerPage = 1; // Reset to page 1 when filters change
    const searchTerm = document.getElementById('contact-picker-search')?.value || '';
    const roleFilter = document.getElementById('contact-picker-role-filter')?.value || '';
    const boroughFilter = document.getElementById('contact-picker-borough-filter')?.value || '';
    renderContactPickerList(searchTerm, roleFilter, boroughFilter);
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
    const selectedContacts = allComposeContacts.filter(c => selectedContactPhones.has(c.phone_number));
    
    container.innerHTML = selectedContacts.map(c => `
        <div class="contact-chip" data-phone="${c.phone_number}">
            <span>${c.name || c.phone_number}</span>
            <span class="chip-remove" onclick="removeContactChip('${c.phone_number}')">
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
        if (phone && !selectedContactPhones.has(phone) && selectedContactPhones.size < MAX_RECIPIENTS) {
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
        applyContactPickerFilters();
    });
    
    // Contact Picker Role Filter
    document.getElementById('contact-picker-role-filter')?.addEventListener('change', (e) => {
        applyContactPickerFilters();
    });
    
    // Contact Picker Borough Filter
    document.getElementById('contact-picker-borough-filter')?.addEventListener('change', (e) => {
        applyContactPickerFilters();
    });
    
    // Advanced Filters Toggle
    document.getElementById('contact-picker-advanced-toggle')?.addEventListener('click', () => {
        const panel = document.getElementById('contact-picker-advanced');
        const btn = document.getElementById('contact-picker-advanced-toggle');
        if (panel && btn) {
            const isVisible = panel.style.display !== 'none';
            panel.style.display = isVisible ? 'none' : 'block';
            btn.classList.toggle('active', !isVisible);
            const icon = btn.querySelector('i');
            if (icon) {
                icon.className = isVisible ? 'fas fa-sliders-h' : 'fas fa-chevron-up';
            }
        }
    });
    
    // Clear Advanced Filters
    document.getElementById('contact-picker-clear-advanced')?.addEventListener('click', () => {
        document.getElementById('contact-picker-neighborhood-filter').value = '';
        document.getElementById('contact-picker-zip-filter').value = '';
        document.getElementById('contact-picker-jobtype-filter').value = '';
        document.getElementById('contact-picker-worktype-filter').value = '';
        document.getElementById('contact-picker-permittype-filter').value = '';
        document.getElementById('contact-picker-status-filter').value = '';
        document.getElementById('contact-picker-bldgtype-filter').value = '';
        document.getElementById('contact-picker-residential-filter').value = '';
        applyContactPickerFilters();
    });
    
    // Advanced Filter Event Listeners
    const advancedFilterIds = [
        'contact-picker-neighborhood-filter', 'contact-picker-zip-filter', 
        'contact-picker-jobtype-filter', 'contact-picker-worktype-filter', 
        'contact-picker-permittype-filter', 'contact-picker-status-filter',
        'contact-picker-bldgtype-filter', 'contact-picker-residential-filter'
    ];
    advancedFilterIds.forEach(id => {
        document.getElementById(id)?.addEventListener('change', () => {
            applyContactPickerFilters();
        });
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
document.addEventListener('DOMContentLoaded', async () => {
    // Hide app and show login screen immediately
    document.querySelector('.app-container').style.display = 'none';
    document.getElementById('login-screen').classList.add('active');
    
    initNavigation();
    initEventListeners();
    initAuthEventListeners();
    
    // Check auth - if logged in, will show app
    const isLoggedIn = await checkAuth();
    if (isLoggedIn) {
        loadDashboard();
    }
});

function initAuthEventListeners() {
    // Login form
    document.getElementById('login-form')?.addEventListener('submit', handleLogin);
    
    // Logout
    document.getElementById('logout-link')?.addEventListener('click', (e) => {
        e.preventDefault();
        handleLogout();
    });
    
    // User menu toggle
    document.getElementById('user-menu-toggle')?.addEventListener('click', () => {
        document.getElementById('user-menu').classList.toggle('active');
    });
    
    // Close user menu when clicking outside
    document.addEventListener('click', (e) => {
        const userMenu = document.getElementById('user-menu');
        const toggle = document.getElementById('user-menu-toggle');
        if (userMenu && toggle && !userMenu.contains(e.target) && !toggle.contains(e.target)) {
            userMenu.classList.remove('active');
        }
    });
    
    // Change password
    document.getElementById('change-password-link')?.addEventListener('click', (e) => {
        e.preventDefault();
        document.getElementById('user-menu').classList.remove('active');
        document.getElementById('password-form').reset();
        showModal('password-modal');
    });
    
    document.getElementById('save-password-btn')?.addEventListener('click', handleChangePassword);
    
    // User management
    document.getElementById('add-user-btn')?.addEventListener('click', showAddUserModal);
    document.getElementById('save-user-btn')?.addEventListener('click', saveUser);
    
    // Campaign event listeners
    initCampaignEventListeners();
}

// ============ Campaigns Module ============

let campaignState = {
    currentStep: 1,
    campaignData: {
        name: '',
        description: '',
        enrollment_type: 'snapshot',
        default_send_time: '11:00',
        filter_criteria: {},
        messages: []
    },
    previewContacts: [],
    previewCount: 0,
    manualContacts: [],  // Manually added contacts
    overlappingPhones: [],
    excludeOverlap: false,
    editingCampaignId: null
};

async function loadCampaigns() {
    const container = document.getElementById('campaigns-list');
    container.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> Loading campaigns...</div>';
    
    try {
        const result = await API.get('/campaigns');
        if (result.success) {
            renderCampaignsList(result.campaigns);
        } else {
            container.innerHTML = '<p class="error">Failed to load campaigns</p>';
        }
    } catch (e) {
        container.innerHTML = '<p class="error">Error loading campaigns</p>';
        console.error(e);
    }
}

function renderCampaignsList(campaigns) {
    const container = document.getElementById('campaigns-list');
    
    if (!campaigns || campaigns.length === 0) {
        container.innerHTML = `
            <div class="no-campaigns-hint" style="text-align: center; padding: 60px; color: var(--text-secondary);">
                <i class="fas fa-bullhorn" style="font-size: 4rem; margin-bottom: 16px; opacity: 0.3;"></i>
                <h3>No Campaigns Yet</h3>
                <p>Create your first campaign to start reaching your contacts with automated message sequences.</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = campaigns.map(campaign => {
        const stats = campaign.stats || {};
        const statusIcon = {
            'draft': '📝',
            'active': '🟢',
            'paused': '🟡',
            'completed': '✅'
        }[campaign.status] || '📝';
        
        return `
            <div class="campaign-card" data-campaign-id="${campaign.id}">
                <div class="campaign-card-header">
                    <h3 class="campaign-card-title">
                        <span>${statusIcon}</span>
                        ${escapeHtml(campaign.name)}
                    </h3>
                    <span class="campaign-status-badge ${campaign.status}">${campaign.status}</span>
                </div>
                <div class="campaign-card-stats">
                    <div class="campaign-stat">
                        <span class="campaign-stat-value">${stats.total_enrolled || 0}</span>
                        <span class="campaign-stat-label">Contacts</span>
                    </div>
                    <div class="campaign-stat">
                        <span class="campaign-stat-value">${campaign.message_count || 0}</span>
                        <span class="campaign-stat-label">Messages</span>
                    </div>
                    <div class="campaign-stat">
                        <span class="campaign-stat-value">${stats.engaged || 0}</span>
                        <span class="campaign-stat-label">Responses</span>
                    </div>
                    <div class="campaign-stat">
                        <span class="campaign-stat-value">${stats.engaged_rate || 0}%</span>
                        <span class="campaign-stat-label">Response Rate</span>
                    </div>
                </div>
                <div class="campaign-card-footer">
                    <span class="campaign-card-info">
                        ${campaign.enrollment_type === 'snapshot' ? '📷 Snapshot' : '🔄 Dynamic'} • 
                        ${campaign.message_count || 0} messages
                    </span>
                    <div class="campaign-card-actions">
                        <button class="btn btn-sm btn-secondary" onclick="viewCampaign(${campaign.id})">
                            <i class="fas fa-eye"></i> View
                        </button>
                        ${campaign.status === 'draft' ? `
                            <button class="btn btn-sm btn-primary" onclick="editCampaign(${campaign.id})">
                                <i class="fas fa-edit"></i> Edit
                            </button>
                        ` : ''}
                        ${campaign.status === 'active' ? `
                            <button class="btn btn-sm btn-warning" onclick="pauseCampaign(${campaign.id})">
                                <i class="fas fa-pause"></i> Pause
                            </button>
                        ` : ''}
                        ${campaign.status === 'paused' ? `
                            <button class="btn btn-sm btn-success" onclick="resumeCampaign(${campaign.id})">
                                <i class="fas fa-play"></i> Resume
                            </button>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

async function viewCampaign(campaignId) {
    document.getElementById('campaigns-list-container').style.display = 'none';
    document.getElementById('campaign-detail-container').style.display = 'block';
    
    const container = document.getElementById('campaign-detail-content');
    container.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> Loading campaign details...</div>';
    
    try {
        const [campaignResult, statsResult] = await Promise.all([
            API.get(`/campaigns/${campaignId}`),
            API.get(`/campaigns/${campaignId}/stats`)
        ]);
        
        if (campaignResult.success) {
            renderCampaignDetail(campaignResult.campaign, statsResult.stats);
        } else {
            container.innerHTML = '<p class="error">Failed to load campaign</p>';
        }
    } catch (e) {
        container.innerHTML = '<p class="error">Error loading campaign</p>';
        console.error(e);
    }
}

function renderCampaignDetail(campaign, stats) {
    const container = document.getElementById('campaign-detail-content');
    const statusIcon = {
        'draft': '📝',
        'active': '🟢',
        'paused': '🟡',
        'completed': '✅'
    }[campaign.status] || '📝';
    
    container.innerHTML = `
        <div class="campaign-detail-header">
            <div>
                <h2 class="campaign-detail-title">${statusIcon} ${escapeHtml(campaign.name)}</h2>
                <div class="campaign-detail-meta">
                    <span><i class="fas fa-calendar"></i> Created: ${formatDate(campaign.created_at)}</span>
                    ${campaign.started_at ? `<span><i class="fas fa-play"></i> Started: ${formatDate(campaign.started_at)}</span>` : ''}
                    <span><i class="fas fa-clock"></i> Send Time: ${campaign.default_send_time} EST</span>
                    <span>${campaign.enrollment_type === 'snapshot' ? '📷 Snapshot' : '🔄 Dynamic'}</span>
                </div>
            </div>
            <div class="campaign-detail-actions">
                <span class="campaign-status-badge ${campaign.status}">${campaign.status}</span>
                ${campaign.status === 'draft' ? `
                    <button class="btn btn-success" onclick="startCampaign(${campaign.id})">
                        <i class="fas fa-rocket"></i> Start Campaign
                    </button>
                ` : ''}
                ${campaign.status === 'active' ? `
                    <button class="btn btn-warning" onclick="pauseCampaign(${campaign.id})">
                        <i class="fas fa-pause"></i> Pause
                    </button>
                ` : ''}
                ${campaign.status === 'paused' ? `
                    <button class="btn btn-success" onclick="resumeCampaign(${campaign.id})">
                        <i class="fas fa-play"></i> Resume
                    </button>
                ` : ''}
            </div>
        </div>
        
        <div class="campaign-detail-stats">
            <div class="campaign-detail-stat-card">
                <div class="campaign-detail-stat-value">${stats?.total_enrolled || 0}</div>
                <div class="campaign-detail-stat-label">Total Enrolled</div>
            </div>
            <div class="campaign-detail-stat-card">
                <div class="campaign-detail-stat-value">${stats?.engaged || 0}</div>
                <div class="campaign-detail-stat-label">Responded</div>
            </div>
            <div class="campaign-detail-stat-card">
                <div class="campaign-detail-stat-value">${stats?.engaged_rate || 0}%</div>
                <div class="campaign-detail-stat-label">Response Rate</div>
            </div>
            <div class="campaign-detail-stat-card">
                <div class="campaign-detail-stat-value">${stats?.opted_out || 0}</div>
                <div class="campaign-detail-stat-label">Opted Out</div>
            </div>
        </div>
        
        <div class="message-sequence">
            <div class="message-sequence-header">
                <i class="fas fa-stream"></i> Message Sequence
            </div>
            ${renderMessageSequence(campaign.messages, stats?.messages)}
        </div>
        
        <div class="engagement-list">
            <div class="engagement-section">
                <div class="engagement-section-header engaged">
                    <i class="fas fa-check-circle"></i> Engaged Contacts (${stats?.engaged_contacts?.length || 0})
                </div>
                <div class="engagement-list-items">
                    ${(stats?.engaged_contacts || []).map(e => `
                        <div class="engagement-item">
                            <div class="engagement-item-name">${escapeHtml(e.contact_name || e.phone_number)}</div>
                            <div class="engagement-item-detail">
                                Responded to Message ${e.first_response_message_id || '?'} • 
                                ${formatDate(e.first_response_at)}
                            </div>
                        </div>
                    `).join('') || '<div class="engagement-item">No responses yet</div>'}
                </div>
            </div>
            <div class="engagement-section">
                <div class="engagement-section-header opted-out">
                    <i class="fas fa-ban"></i> Opted Out (${stats?.opted_out_contacts?.length || 0})
                </div>
                <div class="engagement-list-items">
                    ${(stats?.opted_out_contacts || []).map(e => `
                        <div class="engagement-item">
                            <div class="engagement-item-name">${escapeHtml(e.contact_name || e.phone_number)}</div>
                            <div class="engagement-item-detail">
                                "${escapeHtml(e.opted_out_keyword || 'STOP')}" • 
                                ${formatDate(e.opted_out_at)}
                            </div>
                        </div>
                    `).join('') || '<div class="engagement-item">No opt-outs</div>'}
                </div>
            </div>
        </div>
    `;
}

function renderMessageSequence(messages, messageStats) {
    if (!messages || messages.length === 0) {
        return '<div class="message-sequence-item"><p>No messages in this campaign</p></div>';
    }
    
    const statsMap = {};
    if (messageStats) {
        messageStats.forEach(s => statsMap[s.message_id] = s);
    }
    
    return messages.map((msg, index) => {
        const stats = statsMap[msg.id] || {};
        const statusClass = stats.sent > 0 ? 'sent' : 'pending';
        
        return `
            <div class="message-sequence-item">
                <div class="message-sequence-icon ${statusClass}">
                    ${index + 1}
                </div>
                <div class="message-sequence-content">
                    <div class="message-sequence-title">
                        Message ${index + 1}
                        ${index === 0 ? '(Start)' : `(Day +${msg.days_after_previous})`}
                        ${msg.enable_followup ? '<span class="followup-indicator"><i class="fas fa-redo"></i> Follow-up</span>' : ''}
                        ${msg.has_ab_test ? '<span class="followup-indicator" style="background: #dbeafe; color: #1e40af;"><i class="fas fa-vial"></i> A/B</span>' : ''}
                    </div>
                    <div class="message-sequence-preview">"${escapeHtml(msg.message_body.substring(0, 100))}${msg.message_body.length > 100 ? '...' : ''}"</div>
                    <div class="message-sequence-stats">
                        <span class="message-sequence-stat"><i class="fas fa-paper-plane"></i> ${stats.sent || 0} sent</span>
                        <span class="message-sequence-stat"><i class="fas fa-check-double"></i> ${stats.delivered || 0} delivered</span>
                        <span class="message-sequence-stat"><i class="fas fa-reply"></i> ${stats.responses || 0} responses</span>
                        ${msg.enable_followup ? `<span class="message-sequence-stat"><i class="fas fa-redo"></i> ${stats.followups_sent || 0} follow-ups</span>` : ''}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function backToCampaigns() {
    document.getElementById('campaigns-list-container').style.display = 'block';
    document.getElementById('campaign-detail-container').style.display = 'none';
    loadCampaigns();
}

// Campaign CRUD operations
async function startCampaign(campaignId) {
    if (!confirm('Are you sure you want to start this campaign? Messages will begin sending at the scheduled time.')) {
        return;
    }
    
    try {
        const result = await API.post(`/campaigns/${campaignId}/start`, {});
        if (result.success) {
            showToast('Campaign started successfully!', 'success');
            viewCampaign(campaignId);
        } else {
            showToast(result.error || 'Failed to start campaign', 'error');
        }
    } catch (e) {
        showToast('Error starting campaign', 'error');
    }
}

async function pauseCampaign(campaignId) {
    try {
        const result = await API.post(`/campaigns/${campaignId}/pause`, {});
        if (result.success) {
            showToast('Campaign paused', 'success');
            loadCampaigns();
        } else {
            showToast(result.error || 'Failed to pause campaign', 'error');
        }
    } catch (e) {
        showToast('Error pausing campaign', 'error');
    }
}

async function resumeCampaign(campaignId) {
    try {
        const result = await API.post(`/campaigns/${campaignId}/resume`, {});
        if (result.success) {
            showToast('Campaign resumed', 'success');
            loadCampaigns();
        } else {
            showToast(result.error || 'Failed to resume campaign', 'error');
        }
    } catch (e) {
        showToast('Error resuming campaign', 'error');
    }
}

async function editCampaign(campaignId) {
    // For now, just show the campaign - full edit wizard can be added later
    viewCampaign(campaignId);
}

// Campaign Creation Wizard
function openCampaignWizard() {
    // Reset state
    campaignState = {
        currentStep: 1,
        campaignData: {
            name: '',
            description: '',
            enrollment_type: 'snapshot',
            default_send_time: '11:00',
            filter_criteria: {},
            messages: []
        },
        previewContacts: [],
        previewCount: 0,
        manualContacts: [],
        overlappingPhones: [],
        excludeOverlap: false,
        editingCampaignId: null
    };
    
    // Reset form
    document.getElementById('campaign-name').value = '';
    document.getElementById('campaign-description').value = '';
    document.getElementById('campaign-send-time').value = '11:00';
    document.querySelector('input[name="enrollment-type"][value="snapshot"]').checked = true;
    
    // Reset filters
    document.getElementById('campaign-filter-search').value = '';
    document.getElementById('campaign-filter-borough').value = '';
    document.getElementById('campaign-filter-role').value = '';
    document.getElementById('campaign-filter-jobtype').value = '';
    
    // Reset advanced filters
    const advancedFilters = ['campaign-filter-bldgtype', 'campaign-filter-residential', 
                            'campaign-filter-worktype', 'campaign-filter-status', 'campaign-filter-zip'];
    advancedFilters.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    
    // Reset manual contacts
    document.getElementById('campaign-manual-search').value = '';
    document.getElementById('manual-search-results').style.display = 'none';
    document.getElementById('manual-added-contacts').innerHTML = '';
    document.getElementById('manual-contacts-section').style.display = 'none';
    
    // Reset messages
    document.getElementById('campaign-messages-list').innerHTML = `
        <div class="no-messages-hint">
            <i class="fas fa-envelope-open-text"></i>
            <p>No messages yet. Click "Add Message" to start building your campaign sequence.</p>
        </div>
    `;
    
    // Show step 1
    showWizardStep(1);
    
    showModal('campaign-modal');
}

function showWizardStep(step) {
    campaignState.currentStep = step;
    
    // Update step indicators
    document.querySelectorAll('.wizard-step').forEach(el => {
        const stepNum = parseInt(el.dataset.step);
        el.classList.remove('active', 'completed');
        if (stepNum === step) el.classList.add('active');
        if (stepNum < step) el.classList.add('completed');
    });
    
    // Show/hide content
    for (let i = 1; i <= 4; i++) {
        document.getElementById(`campaign-step-${i}`).style.display = i === step ? 'block' : 'none';
    }
    
    // Update buttons
    document.getElementById('campaign-wizard-back').style.display = step > 1 ? 'inline-flex' : 'none';
    document.getElementById('campaign-wizard-next').style.display = step < 4 ? 'inline-flex' : 'none';
    document.getElementById('campaign-wizard-save').style.display = step === 4 ? 'inline-flex' : 'none';
    
    // Load step-specific data
    if (step === 2) {
        updateCampaignPreview();
    }
    if (step === 4) {
        renderCampaignReview();
    }
}

function wizardNext() {
    if (campaignState.currentStep === 1) {
        // Validate step 1
        const name = document.getElementById('campaign-name').value.trim();
        if (!name) {
            showToast('Please enter a campaign name', 'error');
            return;
        }
        campaignState.campaignData.name = name;
        campaignState.campaignData.description = document.getElementById('campaign-description').value.trim();
        campaignState.campaignData.default_send_time = document.getElementById('campaign-send-time').value;
        campaignState.campaignData.enrollment_type = document.querySelector('input[name="enrollment-type"]:checked').value;
    }
    
    if (campaignState.currentStep === 2) {
        // Validate step 2 - need either filtered contacts or manual contacts
        const totalContacts = campaignState.previewCount + campaignState.manualContacts.length;
        if (totalContacts === 0) {
            showToast('No contacts selected. Use filters or add contacts manually.', 'error');
            return;
        }
        // Save filter criteria
        campaignState.campaignData.filter_criteria = getCampaignFilters();
    }
    
    if (campaignState.currentStep === 3) {
        // Validate step 3
        if (campaignState.campaignData.messages.length === 0) {
            showToast('Please add at least one message', 'error');
            return;
        }
    }
    
    showWizardStep(campaignState.currentStep + 1);
}

function wizardBack() {
    showWizardStep(campaignState.currentStep - 1);
}

function getCampaignFilters() {
    const filters = {};
    const search = document.getElementById('campaign-filter-search')?.value?.trim();
    const borough = document.getElementById('campaign-filter-borough').value;
    const role = document.getElementById('campaign-filter-role').value;
    const jobType = document.getElementById('campaign-filter-jobtype').value;
    const bldgType = document.getElementById('campaign-filter-bldgtype')?.value;
    const residential = document.getElementById('campaign-filter-residential')?.value;
    const workType = document.getElementById('campaign-filter-worktype')?.value;
    const status = document.getElementById('campaign-filter-status')?.value;
    const zip = document.getElementById('campaign-filter-zip')?.value?.trim();
    
    if (search) filters.search = search;
    if (borough) filters.borough = borough;
    if (role) filters.role = role;
    if (jobType) filters.job_type = jobType;
    if (bldgType) filters.bldg_type = bldgType;
    if (residential) filters.residential = residential;
    if (workType) filters.work_type = workType;
    if (status) filters.filing_status = status;
    if (zip) filters.zip = zip;
    
    return filters;
}

let previewDebounceTimer = null;

async function updateCampaignPreview() {
    // Debounce for search input
    clearTimeout(previewDebounceTimer);
    previewDebounceTimer = setTimeout(async () => {
        await doUpdateCampaignPreview();
    }, 300);
}

async function doUpdateCampaignPreview() {
    const filters = getCampaignFilters();
    const countEl = document.getElementById('preview-count-number');
    const filteredCountEl = document.getElementById('filtered-count');
    const listEl = document.getElementById('contacts-preview-list');
    const footerEl = document.getElementById('contacts-preview-footer');
    
    // Show loading state
    if (countEl) countEl.textContent = '...';
    listEl.innerHTML = '<div class="loading-spinner" style="padding: 40px; text-align: center;"><i class="fas fa-spinner fa-spin"></i> Loading contacts...</div>';
    
    try {
        const result = await API.post('/campaigns/preview-enrollment', { filter_criteria: filters });
        if (result.success) {
            campaignState.previewCount = result.count;
            campaignState.previewContacts = result.sample;
            
            // Update total count (filtered + manual)
            const totalCount = result.count + campaignState.manualContacts.length;
            if (countEl) countEl.textContent = totalCount.toLocaleString();
            
            // Update filtered count
            if (filteredCountEl) filteredCountEl.textContent = result.count.toLocaleString();
            
            // Update contacts list
            renderContactsPreview(result.sample, result.count);
            
            // Show footer if more contacts than shown
            if (footerEl) {
                if (result.count > result.sample.length) {
                    document.getElementById('total-contacts-count').textContent = result.count.toLocaleString();
                    footerEl.style.display = 'block';
                } else {
                    footerEl.style.display = 'none';
                }
            }
            
            // Check for overlaps
            if (result.count > 0 && result.sample.length > 0) {
                const phones = result.sample.map(c => c.phone_normalized || c.phone).filter(Boolean);
                if (phones.length > 0) {
                    await checkCampaignOverlap(phones);
                }
            } else {
                document.getElementById('campaign-overlap-warning').style.display = 'none';
            }
        }
    } catch (e) {
        console.error('Preview error:', e);
        listEl.innerHTML = '<div class="contacts-preview-empty"><i class="fas fa-exclamation-circle"></i><p>Error loading contacts</p></div>';
    }
}

function renderContactsPreview(contacts, totalCount) {
    const listEl = document.getElementById('contacts-preview-list');
    
    if (!contacts || contacts.length === 0) {
        listEl.innerHTML = `
            <div class="contacts-preview-empty">
                <i class="fas fa-user-slash"></i>
                <p>No contacts match your filters</p>
                <small>Try adjusting your filter criteria</small>
            </div>
        `;
        return;
    }
    
    listEl.innerHTML = contacts.map(contact => {
        const name = contact.name || contact.owner_name || 'Unknown';
        const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
        const phone = contact.phone_normalized || contact.phone || '';
        const borough = contact.borough || '';
        const role = contact.role || contact.job_type || '';
        
        return `
            <div class="contact-preview-item">
                <div class="contact-preview-avatar">${initials}</div>
                <div class="contact-preview-info">
                    <div class="contact-preview-name">${escapeHtml(name)}</div>
                    <div class="contact-preview-details">${escapeHtml(phone)}${borough ? ' • ' + borough : ''}</div>
                </div>
                ${role ? `<span class="contact-preview-badge">${escapeHtml(role)}</span>` : ''}
            </div>
        `;
    }).join('');
}

function clearCampaignFilters() {
    document.getElementById('campaign-filter-search').value = '';
    document.getElementById('campaign-filter-borough').value = '';
    document.getElementById('campaign-filter-role').value = '';
    document.getElementById('campaign-filter-jobtype').value = '';
    
    // Advanced filters
    const advancedFilters = ['campaign-filter-bldgtype', 'campaign-filter-residential', 
                            'campaign-filter-worktype', 'campaign-filter-status', 'campaign-filter-zip'];
    advancedFilters.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    
    updateCampaignPreview();
}

// Manual Contact Search and Add
async function searchManualContacts() {
    const searchTerm = document.getElementById('campaign-manual-search').value.trim();
    const resultsEl = document.getElementById('manual-search-results');
    
    if (!searchTerm || searchTerm.length < 2) {
        resultsEl.style.display = 'none';
        return;
    }
    
    resultsEl.innerHTML = '<div style="padding: 12px; text-align: center;"><i class="fas fa-spinner fa-spin"></i></div>';
    resultsEl.style.display = 'block';
    
    try {
        const result = await API.get(`/contacts?search=${encodeURIComponent(searchTerm)}&limit=10`);
        if (result.success && result.contacts && result.contacts.length > 0) {
            // Filter out contacts already added manually - normalize phone numbers for comparison
            const normalizePhone = (p) => (p || '').replace(/\D/g, '').slice(-10);
            const addedPhones = new Set(campaignState.manualContacts.map(c => normalizePhone(c.phone || c.phone_normalized)));
            const filteredResults = result.contacts.filter(c => {
                const contactPhone = normalizePhone(c.phone || c.phone_normalized);
                return !addedPhones.has(contactPhone);
            });
            
            if (filteredResults.length === 0) {
                resultsEl.innerHTML = '<div style="padding: 12px; text-align: center; color: var(--text-muted);">All matching contacts already added</div>';
            } else {
                // Store results for click handling
                window._manualSearchResults = filteredResults;
                resultsEl.innerHTML = filteredResults.map((contact, index) => {
                    const name = contact.name || contact.owner_name || 'Unknown';
                    const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
                    const phone = contact.phone_normalized || contact.phone || '';
                    
                    return `
                        <div class="manual-search-item" data-index="${index}">
                            <div class="contact-preview-avatar">${initials}</div>
                            <div class="manual-search-item-info">
                                <div class="manual-search-item-name">${escapeHtml(name)}</div>
                                <div class="manual-search-item-phone">${escapeHtml(phone)}</div>
                            </div>
                            <i class="fas fa-plus-circle add-btn"></i>
                        </div>
                    `;
                }).join('');
                
                // Add click handlers
                resultsEl.querySelectorAll('.manual-search-item').forEach(item => {
                    item.addEventListener('click', () => {
                        const index = parseInt(item.dataset.index);
                        addManualContact(window._manualSearchResults[index]);
                    });
                });
            }
        } else {
            resultsEl.innerHTML = '<div style="padding: 12px; text-align: center; color: var(--text-muted);">No contacts found</div>';
        }
    } catch (e) {
        console.error('Search error:', e);
        resultsEl.innerHTML = '<div style="padding: 12px; text-align: center; color: var(--danger-color);">Error searching</div>';
    }
}

function addManualContact(contact) {
    // Avoid duplicates
    const phone = contact.phone || contact.phone_normalized;
    if (campaignState.manualContacts.some(c => (c.phone || c.phone_normalized) === phone)) {
        showToast('Contact already added', 'error');
        return;
    }
    
    campaignState.manualContacts.push(contact);
    renderManualContacts();
    updateTotalContactCount();
    
    // Clear search
    document.getElementById('campaign-manual-search').value = '';
    document.getElementById('manual-search-results').style.display = 'none';
    
    showToast('Contact added', 'success');
}

function removeManualContact(index) {
    // Remove by index to avoid phone number string issues
    campaignState.manualContacts.splice(index, 1);
    renderManualContacts();
    updateTotalContactCount();
}

function renderManualContacts() {
    const chipsEl = document.getElementById('manual-added-contacts');
    const sectionEl = document.getElementById('manual-contacts-section');
    const listEl = document.getElementById('manual-contacts-list');
    const manualCountEl = document.getElementById('manual-count');
    
    if (campaignState.manualContacts.length === 0) {
        chipsEl.innerHTML = '';
        sectionEl.style.display = 'none';
        return;
    }
    
    // Update chips in filter panel
    chipsEl.innerHTML = campaignState.manualContacts.map((contact, index) => {
        const name = contact.name || contact.owner_name || 'Unknown';
        return `
            <span class="manual-added-chip">
                ${escapeHtml(name.split(' ')[0])}
                <button class="remove-btn" data-remove-index="${index}">&times;</button>
            </span>
        `;
    }).join('');
    
    // Add click handlers for remove buttons
    chipsEl.querySelectorAll('.remove-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            removeManualContact(parseInt(btn.dataset.removeIndex));
        });
    });
    
    // Update preview section
    sectionEl.style.display = 'block';
    manualCountEl.textContent = campaignState.manualContacts.length;
    
    listEl.innerHTML = campaignState.manualContacts.map((contact, index) => {
        const name = contact.name || contact.owner_name || 'Unknown';
        const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
        const phone = contact.phone_normalized || contact.phone || '';
        const borough = contact.borough || '';
        
        return `
            <div class="contact-preview-item">
                <div class="contact-preview-avatar">${initials}</div>
                <div class="contact-preview-info">
                    <div class="contact-preview-name">${escapeHtml(name)}</div>
                    <div class="contact-preview-details">${escapeHtml(phone)}${borough ? ' • ' + borough : ''}</div>
                </div>
                <button class="contact-remove-btn" data-remove-index="${index}" title="Remove">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
    }).join('');
    
    // Add click handlers for preview list remove buttons
    listEl.querySelectorAll('.contact-remove-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            removeManualContact(parseInt(btn.dataset.removeIndex));
        });
    });
}

function updateTotalContactCount() {
    const totalCount = campaignState.previewCount + campaignState.manualContacts.length;
    const countEl = document.getElementById('preview-count-number');
    if (countEl) countEl.textContent = totalCount.toLocaleString();
}

async function checkCampaignOverlap(phones) {
    const warningEl = document.getElementById('campaign-overlap-warning');
    
    try {
        const result = await API.post('/campaigns/check-overlap', { phone_numbers: phones });
        if (result.success && result.has_overlaps) {
            const overlaps = result.overlaps;
            let totalOverlap = 0;
            const campaignNames = [];
            
            for (const [name, phones] of Object.entries(overlaps)) {
                totalOverlap += phones.length;
                campaignNames.push(name);
            }
            
            document.getElementById('campaign-overlap-text').textContent = 
                `${totalOverlap} contacts are already in active campaigns: ${campaignNames.join(', ')}`;
            warningEl.style.display = 'flex';
            
            campaignState.overlappingPhones = Object.values(overlaps).flat();
        } else {
            warningEl.style.display = 'none';
            campaignState.overlappingPhones = [];
        }
    } catch (e) {
        warningEl.style.display = 'none';
    }
}

// Campaign Messages
function openCampaignMessageModal(existingMessage = null) {
    const modal = document.getElementById('campaign-message-modal');
    const title = document.getElementById('campaign-message-modal-title');
    
    if (existingMessage) {
        title.textContent = 'Edit Message';
        document.getElementById('campaign-message-edit-id').value = existingMessage.id || '';
        document.getElementById('campaign-message-body').value = existingMessage.message_body || '';
        document.getElementById('campaign-message-days').value = existingMessage.days_after_previous || 0;
        document.getElementById('campaign-message-time').value = existingMessage.send_time || '';
        document.getElementById('campaign-message-followup').checked = existingMessage.enable_followup || false;
        document.getElementById('campaign-followup-days').value = existingMessage.followup_days || 3;
        document.getElementById('campaign-followup-body').value = existingMessage.followup_body || '';
        document.getElementById('campaign-message-abtest').checked = existingMessage.has_ab_test || false;
        document.getElementById('campaign-abtest-variant-b').value = existingMessage.ab_test?.variant_b_body || '';
    } else {
        title.textContent = 'Add Message';
        document.getElementById('campaign-message-edit-id').value = '';
        document.getElementById('campaign-message-body').value = '';
        document.getElementById('campaign-message-days').value = campaignState.campaignData.messages.length === 0 ? 0 : 3;
        document.getElementById('campaign-message-time').value = '';
        document.getElementById('campaign-message-followup').checked = false;
        document.getElementById('campaign-followup-days').value = 3;
        document.getElementById('campaign-followup-body').value = 'Just following up on my last message. Let me know if you have any questions!';
        document.getElementById('campaign-message-abtest').checked = false;
        document.getElementById('campaign-abtest-variant-b').value = '';
    }
    
    // Show/hide followup options
    document.getElementById('followup-options').style.display = 
        document.getElementById('campaign-message-followup').checked ? 'block' : 'none';
    document.getElementById('abtest-options').style.display = 
        document.getElementById('campaign-message-abtest').checked ? 'block' : 'none';
    
    showModal('campaign-message-modal');
}

function saveCampaignMessage() {
    const body = document.getElementById('campaign-message-body').value.trim();
    if (!body) {
        showToast('Please enter a message', 'error');
        return;
    }
    
    const message = {
        id: Date.now(), // Temporary ID for local tracking
        message_body: body,
        days_after_previous: parseInt(document.getElementById('campaign-message-days').value) || 0,
        send_time: document.getElementById('campaign-message-time').value || null,
        enable_followup: document.getElementById('campaign-message-followup').checked,
        followup_days: parseInt(document.getElementById('campaign-followup-days').value) || 3,
        followup_body: document.getElementById('campaign-followup-body').value || 'Just following up on my last message. Let me know if you have any questions!',
        has_ab_test: document.getElementById('campaign-message-abtest').checked,
        ab_test: document.getElementById('campaign-message-abtest').checked ? {
            variant_b_body: document.getElementById('campaign-abtest-variant-b').value
        } : null
    };
    
    const editId = document.getElementById('campaign-message-edit-id').value;
    if (editId) {
        // Update existing message
        const index = campaignState.campaignData.messages.findIndex(m => m.id == editId);
        if (index >= 0) {
            message.id = parseInt(editId);
            campaignState.campaignData.messages[index] = message;
        }
    } else {
        // Add new message
        campaignState.campaignData.messages.push(message);
    }
    
    renderCampaignMessages();
    hideModal('campaign-message-modal');
}

function renderCampaignMessages() {
    const container = document.getElementById('campaign-messages-list');
    const messages = campaignState.campaignData.messages;
    
    if (messages.length === 0) {
        container.innerHTML = `
            <div class="no-messages-hint">
                <i class="fas fa-envelope-open-text"></i>
                <p>No messages yet. Click "Add Message" to start building your campaign sequence.</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = messages.map((msg, index) => `
        <div class="campaign-message-item" data-message-id="${msg.id}">
            <div class="campaign-message-number">${index + 1}</div>
            <div class="campaign-message-content">
                <div class="campaign-message-text">${escapeHtml(msg.message_body)}</div>
                <div class="campaign-message-meta">
                    <span><i class="fas fa-clock"></i> ${index === 0 ? 'Immediately' : `Day +${msg.days_after_previous}`}</span>
                    ${msg.send_time ? `<span><i class="fas fa-bell"></i> ${msg.send_time}</span>` : ''}
                    ${msg.enable_followup ? `<span><i class="fas fa-redo"></i> Follow-up after ${msg.followup_days} days</span>` : ''}
                    ${msg.has_ab_test ? `<span><i class="fas fa-vial"></i> A/B Test</span>` : ''}
                </div>
            </div>
            <div class="campaign-message-actions">
                <button class="btn-icon" onclick="editCampaignMessage(${msg.id})" title="Edit">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn-icon danger" onclick="deleteCampaignMessage(${msg.id})" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `).join('');
}

function editCampaignMessage(messageId) {
    const message = campaignState.campaignData.messages.find(m => m.id === messageId);
    if (message) {
        openCampaignMessageModal(message);
    }
}

function deleteCampaignMessage(messageId) {
    if (!confirm('Delete this message?')) return;
    
    campaignState.campaignData.messages = campaignState.campaignData.messages.filter(m => m.id !== messageId);
    renderCampaignMessages();
}

function insertCampaignVar(variable) {
    const textarea = document.getElementById('campaign-message-body');
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = textarea.value;
    textarea.value = text.substring(0, start) + variable + text.substring(end);
    textarea.focus();
    textarea.selectionStart = textarea.selectionEnd = start + variable.length;
}

function renderCampaignReview() {
    const data = campaignState.campaignData;
    const container = document.getElementById('campaign-review');
    
    container.innerHTML = `
        <div class="campaign-review-section">
            <h5>Campaign Details</h5>
            <div class="campaign-review-value">${escapeHtml(data.name)}</div>
            ${data.description ? `<p style="color: var(--text-secondary);">${escapeHtml(data.description)}</p>` : ''}
        </div>
        <div class="campaign-review-section">
            <h5>Enrollment</h5>
            <div class="campaign-review-value">
                ${data.enrollment_type === 'snapshot' ? '📷 Snapshot' : '🔄 Dynamic'} • 
                ${campaignState.previewCount} contacts
            </div>
            <p style="color: var(--text-secondary); margin-top: 4px;">
                Filters: ${Object.entries(data.filter_criteria).map(([k, v]) => `${k}: ${v}`).join(', ') || 'None'}
            </p>
        </div>
        <div class="campaign-review-section">
            <h5>Messages (${data.messages.length})</h5>
            ${data.messages.map((msg, i) => `
                <div style="padding: 8px 0; border-bottom: 1px solid var(--border-color);">
                    <strong>Message ${i + 1}</strong> - ${i === 0 ? 'Immediately' : `Day +${msg.days_after_previous}`}
                    ${msg.enable_followup ? '<span style="color: var(--warning-color);"> • Follow-up enabled</span>' : ''}
                    ${msg.has_ab_test ? '<span style="color: var(--primary-color);"> • A/B Test</span>' : ''}
                    <p style="color: var(--text-secondary); margin: 4px 0 0 0; font-size: 0.9rem;">
                        "${escapeHtml(msg.message_body.substring(0, 80))}${msg.message_body.length > 80 ? '...' : ''}"
                    </p>
                </div>
            `).join('')}
        </div>
        <div class="campaign-review-section">
            <h5>Schedule</h5>
            <div class="campaign-review-value">
                Messages sent daily at ${data.default_send_time} EST
            </div>
        </div>
    `;
}

async function saveCampaign() {
    const data = campaignState.campaignData;
    
    try {
        // 1. Create the campaign
        const campaignResult = await API.post('/campaigns', {
            name: data.name,
            description: data.description,
            enrollment_type: data.enrollment_type,
            filter_criteria: data.filter_criteria,
            default_send_time: data.default_send_time
        });
        
        if (!campaignResult.success) {
            showToast(campaignResult.error || 'Failed to create campaign', 'error');
            return;
        }
        
        const campaignId = campaignResult.campaign.id;
        
        // 2. Add messages
        for (const msg of data.messages) {
            const msgResult = await API.post(`/campaigns/${campaignId}/messages`, {
                message_body: msg.message_body,
                days_after_previous: msg.days_after_previous,
                send_time: msg.send_time,
                enable_followup: msg.enable_followup,
                followup_days: msg.followup_days,
                followup_body: msg.followup_body
            });
            
            // If has A/B test, set it up
            if (msg.has_ab_test && msg.ab_test?.variant_b_body && msgResult.success) {
                await API.post(`/campaigns/messages/${msgResult.message.id}/ab-test`, {
                    variant_b_body: msg.ab_test.variant_b_body
                });
            }
        }
        
        // 3. Enroll contacts
        const enrollData = {
            use_filters: true,
            exclude_phones: campaignState.excludeOverlap ? campaignState.overlappingPhones : [],
            manual_contacts: campaignState.manualContacts.map(c => ({
                phone: c.phone || c.phone_normalized,
                name: c.name || c.owner_name || 'Unknown',
                borough: c.borough || '',
                role: c.role || ''
            }))
        };
        const enrollResult = await API.post(`/campaigns/${campaignId}/enroll`, enrollData);
        
        showToast(`Campaign created with ${enrollResult.enrolled_count || 0} contacts enrolled!`, 'success');
        hideModal('campaign-modal');
        loadCampaigns();
        
    } catch (e) {
        showToast('Error creating campaign', 'error');
        console.error(e);
    }
}

// Initialize campaign event listeners
function initCampaignEventListeners() {
    // New campaign button
    document.getElementById('new-campaign-btn')?.addEventListener('click', openCampaignWizard);
    
    // Back to campaigns list
    document.getElementById('back-to-campaigns')?.addEventListener('click', backToCampaigns);
    
    // Wizard navigation
    document.getElementById('campaign-wizard-next')?.addEventListener('click', wizardNext);
    document.getElementById('campaign-wizard-back')?.addEventListener('click', wizardBack);
    document.getElementById('campaign-wizard-save')?.addEventListener('click', saveCampaign);
    
    // Filter changes - basic filters
    ['campaign-filter-borough', 'campaign-filter-role', 'campaign-filter-jobtype'].forEach(id => {
        document.getElementById(id)?.addEventListener('change', updateCampaignPreview);
    });
    
    // Advanced filter changes
    ['campaign-filter-bldgtype', 'campaign-filter-residential', 'campaign-filter-worktype', 
     'campaign-filter-status'].forEach(id => {
        document.getElementById(id)?.addEventListener('change', updateCampaignPreview);
    });
    
    // Search input with debounce
    document.getElementById('campaign-filter-search')?.addEventListener('input', updateCampaignPreview);
    
    // Zip code input
    document.getElementById('campaign-filter-zip')?.addEventListener('input', updateCampaignPreview);
    
    // Advanced filters toggle
    document.getElementById('campaign-advanced-toggle')?.addEventListener('click', () => {
        const advPanel = document.getElementById('campaign-advanced-filters');
        const btn = document.getElementById('campaign-advanced-toggle');
        if (advPanel.style.display === 'none') {
            advPanel.style.display = 'block';
            btn.innerHTML = '<i class="fas fa-sliders-h"></i> Hide Advanced';
        } else {
            advPanel.style.display = 'none';
            btn.innerHTML = '<i class="fas fa-sliders-h"></i> Advanced Filters';
        }
    });
    
    // Clear filters button
    document.getElementById('campaign-clear-filters')?.addEventListener('click', clearCampaignFilters);
    
    // Manual contact search
    document.getElementById('campaign-manual-search-btn')?.addEventListener('click', searchManualContacts);
    document.getElementById('campaign-manual-search')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') searchManualContacts();
    });
    // Hide search results when clicking outside
    document.addEventListener('click', (e) => {
        const resultsEl = document.getElementById('manual-search-results');
        const searchArea = document.querySelector('.manual-search-input-wrapper');
        if (resultsEl && searchArea && !searchArea.contains(e.target)) {
            resultsEl.style.display = 'none';
        }
    });
    
    // Overlap handling
    document.getElementById('campaign-exclude-overlap')?.addEventListener('click', () => {
        campaignState.excludeOverlap = true;
        document.getElementById('campaign-overlap-warning').style.display = 'none';
        showToast('Overlapping contacts will be excluded', 'success');
    });
    
    document.getElementById('campaign-include-overlap')?.addEventListener('click', () => {
        campaignState.excludeOverlap = false;
        document.getElementById('campaign-overlap-warning').style.display = 'none';
        showToast('Overlapping contacts will be included', 'success');
    });
    
    // Add message button
    document.getElementById('add-campaign-message-btn')?.addEventListener('click', () => openCampaignMessageModal());
    
    // Save message button
    document.getElementById('save-campaign-message-btn')?.addEventListener('click', saveCampaignMessage);
    
    // Follow-up checkbox toggle
    document.getElementById('campaign-message-followup')?.addEventListener('change', (e) => {
        document.getElementById('followup-options').style.display = e.target.checked ? 'block' : 'none';
    });
    
    // A/B test checkbox toggle
    document.getElementById('campaign-message-abtest')?.addEventListener('change', (e) => {
        document.getElementById('abtest-options').style.display = e.target.checked ? 'block' : 'none';
    });
}