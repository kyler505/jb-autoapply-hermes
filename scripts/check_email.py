"""Check Gmail for job application responses and alert on high-signal emails.

Run by cron. Exits cleanly with nothing to report, or prints findings.

Output convention: non-empty stdout = deliver; empty stdout = silent (no news is good news).
"""
import json, subprocess, sys
from datetime import datetime, timezone

def gmail_get(path, account='work'):
    tok_file = f'/home/kyler/.hermes/google_token_{account}.json'
    d = json.load(open(tok_file))
    tok = d.get('token', d.get('access_token', ''))
    url = f'https://gmail.googleapis.com/gmail/v1/users/me/{path}'
    res = subprocess.check_output(['curl', '-s', '-H', f'Authorization: Bearer {tok}', url])
    return json.loads(res)

def hr(s):
    return f'\n{"─" * 60}\n{s}\n{"─" * 60}'

# ── Scopes ────────────────────────────────────────────────────────────
# Work (TAMU): where applications go
# Personal: where misc alerts go

accounts = {
    'work':  {'file': '/home/kyler/.hermes/google_token_work.json',  'label': 'TAMU (kcao@tamu.edu)'},
    'personal': {'file': '/home/kyler/.hermes/google_token_personal.json', 'label': 'Personal (kylercao18@gmail.com)'},
}

signals = []
counts = {}

for key, acct in accounts.items():
    try:
        data = gmail_get('messages?q=in:inbox+newer_than:3d&maxResults=30', key)
    except Exception as e:
        # Try to refresh token
        try:
            d = json.load(open(acct['file']))
            r = subprocess.check_output(
                ['curl', '-s', '-X', 'POST', 'https://oauth2.googleapis.com/token',
                 '-d', f'client_id={d["client_id"]}&client_secret={d.get("client_secret","")}&refresh_token={d["refresh_token"]}&grant_type=refresh_token']
            )
            ref = json.loads(r)
            if 'access_token' in ref:
                d['token'] = ref['access_token']
                json.dump(d, open(acct['file'], 'w'), indent=2)
                data = gmail_get('messages?q=in:inbox+newer_than:3d&maxResults=30', key)
            else:
                counts[key] = f'❌ Auth failed — need re-auth'
                continue
        except Exception as e2:
            counts[key] = f'❌ Auth error: {e2}'
            continue

    msgs = data.get('messages', [])
    counts[key] = f'{len(msgs)} messages (3d)'

    for m in msgs:
        try:
            detail = gmail_get(f'messages/{m["id"]}?format=metadata&metadataHeaders=subject&metadataHeaders=from&metadataHeaders=date', key)
        except:
            continue
        headers = {h['name']: h['value'] for h in detail.get('payload',{}).get('headers',[])}
        subj = (headers.get('Subject') or '').strip()
        fr = (headers.get('From') or '').strip()
        dt = (headers.get('Date') or '')[:25]

        low = subj.lower()

        # Priority signals — these always alert
        priority = False

        # Interview/offer/rejection signals
        if any(k in low for k in [
            'interview', 'offer letter', 'we\'d like to meet', 'schedule an interview',
            'next steps', 'congratulations', 'you\'ve been selected',
            'regret to inform', 'unfortunately', 'not moving forward',
            'application status update',
        ]):
            priority = True

        # Company-specific match — applications we've sent recently
        # Check against a list of applied companies (we can't list all, so use broad heuristics)
        if any(k in low for k in [
            'output biosci', 'transcend', 'ixl learning', 'leidos',
            'spacex', '1password', 'muru', 'kinaxis',
            'mindsmith', 'rivian', 'volkswagen', 'veeva',
            'baker hughes', 'cox', 'kla', 'sentry', 'intel', 'boeing',
            'sandhills', 'corning', 'four hands', 'delta', 'microsoft',
            'dat freight',
        ]):
            priority = True

        # Workday OTP / account creation — low signal, batch summary only
        is_otp = 'otp.workday' in fr.lower() or ('verify your candidate account' in low)

        signals.append({
            'account': acct['label'],
            'from': fr,
            'subject': subj,
            'date': dt,
            'priority': priority,
            'otp': is_otp,
        })

# ── Output ────────────────────────────────────────────────────────────

non_otp = [s for s in signals if not s['otp']]
otps = [s for s in signals if s['otp']]

# Always output counts
print(f"📬 Email Check — {datetime.now().strftime('%b %d, %H:%M')}")
print(f"   {counts.get('work', '?')}  |  {counts.get('personal', '?')}")

priority_signals = [s for s in non_otp if s['priority']]
other_signals = [s for s in non_otp if not s['priority']]

if priority_signals:
    print(hr("🔴 APPLICATION RESPONSES — PRIORITY"))
    for s in priority_signals:
        print(f"  [{s['account']}] {s['date']}")
        print(f"  From: {s['from']}")
        print(f"  Subject: {s['subject']}")
        print()

if otps:
    print(hr("🔐 Workday Account Verifications (OTPs)"))
    for s in otps:
        print(f"  {s['date'][:16]}  {s['from'][:40]}  {s['subject'][:60]}")

if other_signals:
    print(hr("📄 Other Recent Mail"))
    for s in other_signals[:8]:
        print(f"  {'⬆' if s['priority'] else '·'} [{s['account']}] {s['date'][:16]}  {s['from'][:35]}  {s['subject'][:60]}")

if not any([priority_signals, otps, other_signals]):
    print(hr("📭 Nothing new — all clear"))
    sys.exit(0)
