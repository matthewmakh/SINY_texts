# Contact Picker System

## Overview

The Contact Picker is a modal dialog for selecting SMS recipients. It loads contacts from the PostgreSQL leads database and allows filtering, searching, and pagination.

## Data Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                        Contact Picker Modal                       │
├──────────────────────────────────────────────────────────────────┤
│  1. User opens "Select Contacts" button                          │
│  2. loadComposeView() fetches /api/contacts?mobile_only=true     │
│  3. All 17k contacts stored in allComposeContacts array          │
│  4. renderContactPickerList() displays 500 per page              │
│  5. Filters applied client-side for instant feedback             │
│  6. Selected contacts stored in selectedContactPhones Set        │
└──────────────────────────────────────────────────────────────────┘
```

## UI Structure

```html
<div class="modal" id="contact-picker-modal">
  ├── Search Bar (#contact-picker-search)
  ├── Basic Filters
  │   ├── Role Dropdown (#contact-picker-role-filter)
  │   └── Borough Dropdown (#contact-picker-borough-filter)
  ├── Action Buttons
  │   ├── Select All Visible
  │   ├── Clear All
  │   └── Advanced Filters Toggle
  ├── Advanced Filters Panel (#contact-picker-advanced)
  │   ├── Neighborhood (#contact-picker-neighborhood-filter)
  │   ├── Zip Code (#contact-picker-zip-filter)
  │   ├── Job Type (#contact-picker-jobtype-filter)
  │   ├── Work Type (#contact-picker-worktype-filter)
  │   ├── Permit Type (#contact-picker-permittype-filter)
  │   ├── Permit Status (#contact-picker-status-filter)
  │   ├── Building Type (#contact-picker-bldgtype-filter)
  │   └── Residential (#contact-picker-residential-filter)
  ├── Filtered Count Display (#contact-picker-filtered-count)
  ├── Contact List (#contact-picker-list)
  ├── Pagination (#contact-picker-pagination)
  └── Footer (Cancel / Confirm Selection)
</div>
```

## JavaScript Functions

### Core Functions

```javascript
// Load all contacts on compose view init
async function loadComposeView() {
    const response = await API.get('/contacts?mobile_only=true&limit=100000');
    allComposeContacts = response.success ? response.contacts : [];
}

// Load dynamic filter options (neighborhoods, zip codes)
async function loadFilterOptions() {
    const response = await API.get('/contacts/filter-options');
    // Populates neighborhood and zip dropdowns
}

// Main render function
function renderContactPickerList(searchTerm, roleFilter, boroughFilter) {
    // 1. Get advanced filters
    // 2. Apply all filters to allComposeContacts
    // 3. Paginate results
    // 4. Render HTML
    // 5. Attach click handlers
}

// Pagination render
function renderContactPickerPagination(totalContacts, totalPages) {
    // Shows "Showing X-Y of Z" and Prev/Next buttons
}

// Apply filters (called by event listeners)
function applyContactPickerFilters(resetPage = true) {
    if (resetPage) contactPickerPage = 1;
    renderContactPickerList(...);
}
```

### Helper Functions

```javascript
// Get all advanced filter values as object
function getAdvancedFilters() {
    return {
        neighborhood: ...,
        zip_code: ...,
        job_type: ...,
        work_type: ...,
        permit_type: ...,
        permit_status: ...,
        bldg_type: ...,
        residential: ...
    };
}

// Check if any advanced filter is active
function hasAdvancedFilters() {
    const filters = getAdvancedFilters();
    return Object.values(filters).some(v => v !== '');
}
```

## Filter Logic

Filters are applied sequentially in this order:

```javascript
let filtered = allComposeContacts;

// 1. Search (name, phone, company)
if (searchTerm) {
    filtered = filtered.filter(c => 
        c.name?.toLowerCase().includes(term) ||
        c.phone_number?.includes(term) ||
        c.company?.toLowerCase().includes(term)
    );
}

// 2. Role filter (Owner, Permittee)
if (roleFilter) {
    filtered = filtered.filter(c => c.role === roleFilter);
}

// 3. Borough filter
if (boroughFilter) {
    filtered = filtered.filter(c => c.borough === boroughFilter);
}

// 4-11. Advanced filters
if (advFilters.neighborhood) {
    filtered = filtered.filter(c => c.neighborhood === advFilters.neighborhood);
}
// ... same pattern for all 8 advanced filters
```

## Pagination

```javascript
const CONTACTS_PER_PAGE = 500;
let contactPickerPage = 1;

// Calculate pagination
const totalPages = Math.ceil(filtered.length / CONTACTS_PER_PAGE);
const startIdx = (contactPickerPage - 1) * CONTACTS_PER_PAGE;
const endIdx = startIdx + CONTACTS_PER_PAGE;
const pageContacts = filtered.slice(startIdx, endIdx);
```

## Contact Object Structure

Each contact from the API has these fields:

```javascript
{
    id: 12345,
    phone_number: "+12125551234",
    name: "John Smith",
    company: "ABC Construction",
    permit_number: "123456789",
    address: "123 Main St, Manhattan",
    role: "Owner",                    // or "Permittee"
    source: "permit_contact",         // or "manual"
    is_mobile: true,
    borough: "MANHATTAN",
    neighborhood: "Midtown-Midtown South",
    zip_code: "10001",
    job_type: "A1",
    work_type: "OT",
    permit_type: "AL",
    permit_status: "ISSUED",
    bldg_type: "2",
    residential: "YES"
}
```

## Selection Management

```javascript
// Global Set to track selected phone numbers
let selectedContactPhones = new Set();

// Max recipients (safety limit)
const MAX_RECIPIENTS = 50;

// Add/remove on click
if (selectedContactPhones.has(phone)) {
    selectedContactPhones.delete(phone);
} else {
    if (selectedContactPhones.size >= MAX_RECIPIENTS) {
        showToast(`Maximum ${MAX_RECIPIENTS} recipients allowed`, 'error');
        return;
    }
    selectedContactPhones.add(phone);
}
```

## Event Listeners

```javascript
// Search input (debounced via input event)
document.getElementById('contact-picker-search')?.addEventListener('input', () => {
    applyContactPickerFilters();
});

// All filter dropdowns
['contact-picker-role-filter', 'contact-picker-borough-filter', 
 'contact-picker-neighborhood-filter', 'contact-picker-zip-filter',
 ...].forEach(id => {
    document.getElementById(id)?.addEventListener('change', () => {
        applyContactPickerFilters();
    });
});

// Advanced filters toggle
document.getElementById('contact-picker-advanced-toggle')?.addEventListener('click', () => {
    const panel = document.getElementById('contact-picker-advanced');
    panel.style.display = panel.style.display !== 'none' ? 'none' : 'block';
});

// Clear advanced filters
document.getElementById('contact-picker-clear-advanced')?.addEventListener('click', () => {
    // Reset all 8 advanced filter dropdowns to ''
    applyContactPickerFilters();
});
```

## CSS Classes

| Class | Purpose |
|-------|---------|
| `.contact-picker-filters` | Container for search and filter row |
| `.contact-picker-filter-row` | Horizontal row of filters |
| `.contact-picker-advanced` | Collapsible advanced filters panel |
| `.advanced-filters-grid` | 2-column CSS grid for filters |
| `.advanced-filter-group` | Single filter (label + select) |
| `.contact-picker-list` | Scrollable contact list (max-height: 350px) |
| `.contact-picker-item` | Single contact row |
| `.contact-picker-item.selected` | Selected state (blue background) |
| `.contact-picker-pagination` | Pagination bar at bottom |
| `.contact-picker-filtered-count` | "X of Y contacts match" display |
