# Changelog

## December 29-30, 2025

### Authentication System (Staging Branch)

Added full authentication system with role-based access control to the SMS Dashboard. Currently on `staging` branch for testing.

#### Features

- **Login Screen**: Full-screen overlay requiring authentication
- **User Management**: Admin-only interface to create/edit/delete users
- **Role-Based Access**: 4 roles with different permission levels
- **Session Management**: Token-based sessions with 7-day expiry
- **Password Security**: SHA-256 hashing with salt and 10k iterations
- **Shared Auth**: Same credentials work across SMS and Permits dashboards

#### Roles

| Role | Access Level |
|------|--------------|
| admin | Full access, can manage users |
| manager | Send messages, view all data, manage contacts |
| agent | Send messages, view assigned data |
| viewer | Read-only access |

#### New Files

- `auth.py` - Authentication module (700+ lines)
  - Password hashing/verification
  - Session management
  - User CRUD operations
  - Decorators: `@login_required`, `@role_required`, `@permission_required`

#### Modified Files

- `app.py` - Added auth routes and middleware
- `templates/index.html` - Login screen, user management UI, user menu
- `static/css/style.css` - Auth styles (login screen, user table, role badges)
- `static/js/app.js` - Auth handling, login/logout, user management

#### Database Tables (PostgreSQL)

- `auth_users` - User accounts
- `auth_sessions` - Active sessions
- `auth_roles` - Role definitions
- `auth_activity_log` - Activity tracking

#### Default Admin

- Email: `matt@tyeny.com`
- Password: `changeme123!`
- **⚠️ Change immediately after first login**

---

## December 27-29, 2025

### Advanced Filters for Contact Picker

Added comprehensive filtering system to the contact picker modal, allowing users to target specific contacts based on permit data.

#### New Filters (8 total)

| Filter | Field | Options |
|--------|-------|---------|
| Neighborhood | `nta_name` | Dynamic - Top 50 by permit count |
| Zip Code | `zip_code` | Dynamic - Top 50 by permit count |
| Job Type | `job_type` | A1, A2, A3, NB, DM, SG |
| Work Type | `work_type` | OT, PL, EQ, MH, SP, FP, BL, SD |
| Permit Type | `permit_type` | EW, PL, EQ, AL, NB, DM, SG, FO |
| Permit Status | `permit_status` | ISSUED, RE-ISSUED, IN PROCESS |
| Building Type | `bldg_type` | 1 (One/Two Family), 2 (Multiple Dwelling) |
| Residential | `residential` | YES, (blank for all) |

#### Files Modified

**Backend:**
- `leads_service.py`
  - `search_contacts()` - Added 8 new filter parameters
  - `get_all_contacts()` - Pass-through for new filters
  
- `app.py`
  - `/api/contacts` - Accept and apply all advanced filters
  - `/api/contacts/filter-options` - NEW endpoint for neighborhoods/zip codes

**Frontend:**
- `templates/index.html`
  - Added collapsible "Advanced Filters" panel
  - 8 dropdown selects in 2-column grid
  - Toggle button and clear filters button

- `static/css/style.css`
  - `.contact-picker-advanced` - Panel styling
  - `.advanced-filters-grid` - 2-column responsive grid
  - `.advanced-filter-group` - Individual filter styling
  - `.btn-outline` - Toggle button styling

- `static/js/app.js`
  - `loadFilterOptions()` - Fetch neighborhoods/zips from API
  - `getAdvancedFilters()` - Collect filter values
  - `hasAdvancedFilters()` - Check if any advanced filter is set
  - Updated `renderContactPickerList()` - Apply all filters
  - Event listeners for all 8 filter dropdowns
  - Toggle and clear button handlers

---

### Pagination for Contact Picker

Implemented client-side pagination to handle large contact lists efficiently.

#### Changes

- **Removed 500 contact limit** → Now loads up to 100,000 contacts
- **500 contacts per page** with navigation
- Shows "Showing 1-500 of 17,050" and "Page 1 of 35"

#### Implementation Details

**New Variables:**
```javascript
let contactPickerPage = 1;
const CONTACTS_PER_PAGE = 500;
```

**New Function:**
```javascript
function renderContactPickerPagination(totalContacts, totalPages)
```

**Modified:**
- `loadComposeView()` - Reset page to 1, increased limit
- `renderContactPickerList()` - Slice contacts for current page
- `applyContactPickerFilters(resetPage = true)` - Optional page reset

**CSS Added:**
```css
.contact-picker-pagination
.pagination-info
.pagination-controls
.pagination-current
```

---

### Contact Display Improvements

Enhanced how contacts appear in the picker list.

#### Smart Name Fallback
```javascript
let displayName = c.name;
const isNameEmpty = !displayName || displayName === 'NA' || displayName === 'N/A';
if (isNameEmpty && c.company) {
    displayName = c.company;
} else if (isNameEmpty) {
    displayName = 'Unknown';
}
```

#### Additional Fields Shown
- Address (from permit)
- Company (if different from name)
- Role tag (Owner/Permittee)
- Borough tag
- "Manual" tag for manually added contacts

---

### CSS Fixes

- Fixed advanced filters overflow - changed from 4-column to 2-column grid
- Added `min-width: 0` and `box-sizing: border-box` to prevent overflow
- Reduced padding and font sizes for compact display

---

## Database Stats (as of Dec 29, 2025)

```
Total unique mobile contacts: 17,050
  - Owner: 13,080
  - Permittee: 3,970

No duplicate phone numbers (1.00 records per phone)
```
