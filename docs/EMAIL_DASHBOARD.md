# Email Dashboard (Instantly-style)

The Email module turns this app into a cold-email platform alongside the SMS one. It connects multiple Gmail / Workspace mailboxes via OAuth, rotates sends across them with per-inbox daily caps and jitter, generates AI-personalized openers via Claude, tracks opens / clicks / replies, and auto-stops sequences when a recipient replies or unsubscribes.

## What's included

- Gmail / Google Workspace OAuth — connect any number of sending mailboxes
- Multi-inbox rotation with per-inbox daily caps and configurable jitter
- Multi-step sequences with same-thread follow-ups (Re: ...)
- Subject-line A/B testing (random 50/50 assignment per enrollment)
- AI-personalized opening lines via Claude (`{ai_first_line}` token)
- Spintax: `{spin:Hi|Hey|Hello}`
- Template variables: `{first_name}`, `{name}`, `{company}`, `{email}`, plus any field from `extra_data`
- Open + click tracking (1×1 pixel + link rewrite)
- Reply detection via Gmail History API polling (every 2 minutes)
- Auto-stop on reply; auto-mark on bounce / out-of-office
- One-click unsubscribe with proper List-Unsubscribe headers (Gmail 2024 compliance)
- Global suppression list — once unsubscribed, never email again
- Send windows (timezone-aware, day-of-week filter)
- Unified inbox view for replies across all connected mailboxes
- Dashboard with send / open / reply / click / bounce rates per campaign and per inbox

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

This adds `requests` and `anthropic` (already on PyPI; no system packages needed).

### 2. Create a Google Cloud OAuth client

You need an OAuth 2.0 Web Application client with these scopes:

- `openid email profile`
- `https://www.googleapis.com/auth/gmail.send`
- `https://www.googleapis.com/auth/gmail.modify`
- `https://www.googleapis.com/auth/gmail.readonly`

Steps:

1. Go to <https://console.cloud.google.com/apis/credentials>
2. Create Project (or pick an existing one)
3. Enable the Gmail API: APIs & Services → Library → search "Gmail API" → Enable
4. OAuth consent screen → External → fill in app name, support email, etc. Add the three Gmail scopes above + `openid`, `email`, `profile`. While in "Testing" mode, add yourself as a test user.
5. Credentials → Create credentials → OAuth client ID → Web application
6. Authorized redirect URI: `{PUBLIC_BASE_URL}/api/email/oauth/callback`  
   - Local: `http://localhost:5000/api/email/oauth/callback`
   - Railway: `https://your-app.up.railway.app/api/email/oauth/callback`
7. Copy the **Client ID** and **Client secret** into your env:

```env
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-...
PUBLIC_BASE_URL=https://your-app.up.railway.app
```

While the consent screen is in "Testing" mode you can connect up to 100 mailboxes from your test-user list. To go beyond that, submit the app for verification.

### 3. (Optional) Anthropic key for AI personalization

```env
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

`claude-haiku-4-5` is the default — fast and cheap for one-liners. Switch to `claude-sonnet-4-6` for higher quality.

### 4. Deploy

The new tables are created automatically on startup via `Base.metadata.create_all`. No manual migration needed.

For Railway, add the four new env vars (`PUBLIC_BASE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ANTHROPIC_API_KEY`) and redeploy.

## How sending works

1. **Queue**: every 60s, `_process_email_campaigns` checks each active campaign. For each enrollment whose next step is due AND not opted-out/replied/bounced, it inserts an `EmailSend` row with status `pending`.
2. **Drain**: every 20s, `_drain_email_send_queue` picks one pending send per available inbox (respecting daily cap + last-send jitter floor) and sends it via the Gmail API.
3. **Track**: the email body has a 1×1 GIF and rewritten links pointing back to `/api/email/track/{open,click}/...`.
4. **Replies**: every 2 minutes, each connected inbox is polled via the Gmail History API. Any new INBOX message matching an active enrollment (by thread or sender) sets `first_reply_at` and stops the sequence.

## Schema additions

All in `database.py`:

| Table | Purpose |
|-------|---------|
| `email_accounts` | Connected sending mailboxes (OAuth tokens, daily caps, health) |
| `email_campaigns` | Campaign definition |
| `email_campaign_messages` | Sequence steps (subject, body, delay) |
| `email_enrollments` | Per-recipient state (current step, AI opener, engagement) |
| `email_sends` | Audit log of every outbound email |
| `email_events` | Open / click / reply / unsubscribe events |
| `email_unsubscribes` | Global suppression list |
| `email_replies` | Captured inbound replies (powers the inbox view) |

## API endpoints

```
GET    /api/email/accounts                    List connected mailboxes
PUT    /api/email/accounts/<id>               Update cap / jitter / status
DELETE /api/email/accounts/<id>               Disconnect mailbox
POST   /api/email/accounts/<id>/poll          Force reply poll for one mailbox

GET    /api/email/oauth/start                 Returns Google consent URL
GET    /api/email/oauth/callback              OAuth landing — closes popup

GET    /api/email/campaigns                   List campaigns
POST   /api/email/campaigns                   Create campaign (draft)
GET    /api/email/campaigns/<id>              Get campaign with messages
PUT    /api/email/campaigns/<id>              Update campaign
DELETE /api/email/campaigns/<id>              Delete
POST   /api/email/campaigns/<id>/messages     Add sequence step
PUT    /api/email/messages/<id>               Update step
DELETE /api/email/messages/<id>               Delete step

POST   /api/email/campaigns/<id>/enroll       Enroll: {contacts: [...]} or {use_filters: true}
GET    /api/email/campaigns/<id>/enrollments  List enrollments

POST   /api/email/campaigns/<id>/start        Launch campaign
POST   /api/email/campaigns/<id>/pause        Pause
POST   /api/email/campaigns/<id>/resume       Resume
POST   /api/email/campaigns/<id>/complete     Mark complete

GET    /api/email/inbox                       Unified inbox of replies
POST   /api/email/inbox/<id>/read             Mark reply read

GET    /api/email/track/open/<send_id>.gif    Open tracking pixel (public)
GET    /api/email/track/click/<send_id>?u=    Click redirect (public)
GET    /api/email/unsubscribe/<token>         One-click unsubscribe (public)

GET    /api/email/stats                       Dashboard metrics + account summary
```

## Safety defaults

- Per-inbox daily cap: **50 sends/day** (configurable per account)
- Jitter between sends from same inbox: **45–180 seconds** (configurable)
- Global suppression list enforced before every send
- List-Unsubscribe header on every outbound email (Gmail/Yahoo 2024 requirement)
- Reply auto-stops the sequence — no more follow-ups
- Bounce / out-of-office detection stops the sequence and increments the inbox's `bounce_count_7d`

## Personalization tokens

Available in subject and body:

| Token | Source |
|-------|--------|
| `{first_name}` | First word of `enrollment.name` |
| `{name}` | Full name |
| `{company}` | Company |
| `{email}` | Recipient email |
| `{ai_first_line}` | Generated by Claude on first send when AI is enabled |
| `{anything_else}` | Any key in `enrollment.extra_data` JSON |

Spintax: `{spin:Hi|Hey|Hello}` picks one at render time per recipient.

## Reply detection notes

We poll via the Gmail **History API** rather than Pub/Sub for simplicity — no Cloud project setup beyond the OAuth client. History expires after ~7 days; if the app is offline for that long, the history cursor resets on next poll (we'll miss old replies but not new ones).

For higher-volume use, swap the poll loop in `email_service.py:poll_replies_for_account` for a Pub/Sub watch subscription.
