"""
Service to query leads directly from the Railway PostgreSQL database.
No syncing - contacts are always fetched live from the source.
"""
from sqlalchemy import create_engine, text
from config import Config


_engine = None

def get_leads_engine():
    """Get connection to the external leads database (singleton)"""
    global _engine
    if _engine is None:
        if not Config.LEADS_DATABASE_URL:
            raise Exception("LEADS_DATABASE_URL not configured")
        _engine = create_engine(Config.LEADS_DATABASE_URL, pool_pre_ping=True)
    return _engine


def get_leads_stats():
    """Get stats about available leads"""
    engine = get_leads_engine()
    
    with engine.connect() as conn:
        # From contacts table
        total_contacts = conn.execute(text("SELECT COUNT(*) FROM contacts")).scalar()
        mobile_contacts = conn.execute(text("SELECT COUNT(*) FROM contacts WHERE is_mobile = true")).scalar()
        
        # From owner_contacts table (for future use)
        owner_contacts = conn.execute(text("SELECT COUNT(*) FROM owner_contacts")).scalar()
        
        return {
            'total_contacts': total_contacts,
            'mobile_contacts': mobile_contacts,
            'owner_contacts': owner_contacts
        }


def search_contacts(search: str = None, mobile_only: bool = True, limit: int = 100, offset: int = 0):
    """
    Search contacts from the leads database.
    Combines permit contacts and owner contacts.
    """
    engine = get_leads_engine()
    
    # Build query for permit contacts
    query = """
        SELECT DISTINCT ON (c.phone)
            c.id,
            c.name,
            c.phone,
            c.role,
            c.is_mobile,
            c.carrier_name,
            'permit_contact' as source,
            p.permit_no,
            p.address,
            p.owner_business_name as company
        FROM contacts c
        LEFT JOIN permit_contacts pc ON c.id = pc.contact_id
        LEFT JOIN permits p ON pc.permit_id = p.id
        WHERE c.phone IS NOT NULL 
        AND c.phone != ''
    """
    
    params = {}
    
    if mobile_only:
        query += " AND c.is_mobile = true"
    
    if search:
        query += """ AND (
            c.name ILIKE :search 
            OR c.phone ILIKE :search 
            OR p.owner_business_name ILIKE :search
            OR p.address ILIKE :search
        )"""
        params['search'] = f'%{search}%'
    
    query += " ORDER BY c.phone, c.updated_at DESC"
    query += f" LIMIT {limit} OFFSET {offset}"
    
    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        contacts = [dict(row._mapping) for row in result]
        
        # Normalize phone numbers for display
        for c in contacts:
            c['phone_normalized'] = normalize_phone(c['phone'])
        
        return contacts


def get_contact_by_phone(phone: str):
    """Get a contact by phone number"""
    engine = get_leads_engine()
    
    # Normalize the phone for comparison
    digits = ''.join(c for c in str(phone) if c.isdigit())
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]  # Remove leading 1
    
    query = """
        SELECT 
            c.id,
            c.name,
            c.phone,
            c.role,
            c.is_mobile,
            c.carrier_name,
            'permit_contact' as source,
            p.permit_no,
            p.address,
            p.owner_business_name as company
        FROM contacts c
        LEFT JOIN permit_contacts pc ON c.id = pc.contact_id
        LEFT JOIN permits p ON pc.permit_id = p.id
        WHERE c.phone = :phone
        LIMIT 1
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query), {'phone': digits})
        row = result.fetchone()
        
        if row:
            contact = dict(row._mapping)
            contact['phone_normalized'] = normalize_phone(contact['phone'])
            return contact
        
        return None


def get_owner_contacts(search: str = None, limit: int = 100, offset: int = 0):
    """
    Get contacts from the owner_contacts table.
    This table will be populated in the future.
    """
    engine = get_leads_engine()
    
    query = """
        SELECT 
            id,
            owner_name as name,
            phone,
            phone_type,
            email,
            is_verified,
            confidence,
            source,
            'owner_contact' as contact_source
        FROM owner_contacts
        WHERE phone IS NOT NULL AND phone != ''
    """
    
    params = {}
    
    if search:
        query += """ AND (
            owner_name ILIKE :search 
            OR phone ILIKE :search
        )"""
        params['search'] = f'%{search}%'
    
    query += f" ORDER BY created_at DESC LIMIT {limit} OFFSET {offset}"
    
    with engine.connect() as conn:
        result = conn.execute(text(query), params)
        contacts = [dict(row._mapping) for row in result]
        
        for c in contacts:
            c['phone_normalized'] = normalize_phone(c['phone'])
        
        return contacts


def get_all_contacts(search: str = None, mobile_only: bool = True, source: str = 'all', limit: int = 100, offset: int = 0):
    """
    Get contacts from both permit contacts and owner contacts.
    
    Args:
        search: Search term
        mobile_only: Only return mobile numbers (for permit contacts)
        source: 'permit', 'owner', or 'all'
        limit: Max results
        offset: Pagination offset
    """
    contacts = []
    
    if source in ['all', 'permit']:
        permit_contacts = search_contacts(search, mobile_only, limit, offset)
        contacts.extend(permit_contacts)
    
    if source in ['all', 'owner']:
        owner_contacts = get_owner_contacts(search, limit, offset)
        contacts.extend(owner_contacts)
    
    # Sort by name and dedupe by phone
    seen_phones = set()
    unique_contacts = []
    for c in contacts:
        phone = c.get('phone')
        if phone and phone not in seen_phones:
            seen_phones.add(phone)
            unique_contacts.append(c)
    
    return unique_contacts[:limit]


def get_contacts_by_phones(phones: list):
    """Get multiple contacts by their phone numbers"""
    if not phones:
        return []
    
    engine = get_leads_engine()
    
    # Normalize phones for comparison
    normalized = []
    for phone in phones:
        digits = ''.join(c for c in str(phone) if c.isdigit())
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]
        normalized.append(digits)
    
    placeholders = ','.join([f"'{p}'" for p in normalized])
    
    query = f"""
        SELECT 
            c.id,
            c.name,
            c.phone,
            c.role,
            c.is_mobile,
            c.carrier_name,
            p.permit_no,
            p.address,
            p.owner_business_name as company
        FROM contacts c
        LEFT JOIN permit_contacts pc ON c.id = pc.contact_id
        LEFT JOIN permits p ON pc.permit_id = p.id
        WHERE c.phone IN ({placeholders})
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query))
        contacts = [dict(row._mapping) for row in result]
        
        for c in contacts:
            c['phone_normalized'] = normalize_phone(c['phone'])
        
        return contacts


def get_total_contact_count(mobile_only: bool = True, source: str = 'all'):
    """Get total count of contacts for pagination"""
    engine = get_leads_engine()
    total = 0
    
    with engine.connect() as conn:
        if source in ['all', 'permit']:
            query = "SELECT COUNT(DISTINCT phone) FROM contacts WHERE phone IS NOT NULL AND phone != ''"
            if mobile_only:
                query += " AND is_mobile = true"
            total += conn.execute(text(query)).scalar()
        
        if source in ['all', 'owner']:
            query = "SELECT COUNT(*) FROM owner_contacts WHERE phone IS NOT NULL AND phone != ''"
            total += conn.execute(text(query)).scalar()
    
    return total


def normalize_phone(phone):
    """Normalize phone number to +1XXXXXXXXXX format"""
    if not phone:
        return None
    
    digits = ''.join(c for c in str(phone) if c.isdigit())
    
    if len(digits) == 10:
        return f'+1{digits}'
    elif len(digits) == 11 and digits.startswith('1'):
        return f'+{digits}'
    elif len(digits) == 11:
        return f'+{digits}'
    
    return None


if __name__ == '__main__':
    print("=== Leads Database Stats ===\n")
    stats = get_leads_stats()
    print(f"Permit Contacts: {stats['total_contacts']:,}")
    print(f"  - Mobile: {stats['mobile_contacts']:,}")
    print(f"Owner Contacts: {stats['owner_contacts']:,}")
    
    print("\n=== Sample Contacts ===\n")
    contacts = get_all_contacts(mobile_only=True, limit=5)
    for c in contacts:
        print(f"  {c['name']} | {c['phone_normalized']} | {c.get('role', 'N/A')} | {c.get('source', 'N/A')}")
