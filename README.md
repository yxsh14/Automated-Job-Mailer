# Email Automation Service

Sends personalized job-application emails to HR contacts — 20 per day, with random intervals between 9 AM and 4 PM. Supports both **local Excel** and **Google Sheets** as the contacts backend.

---

## Quick Start (Local)

```bash
# 1. Clone and install
git clone <your-repo>
cd AutoMailer
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env — add your Gmail address and App Password

# 3. Add your files
# Place contacts.xlsx in data/
# Place resume.pdf in data/

# 4. Test — send 1 email right now
python main.py --now

# 5. Run the full scheduler (9 AM – 4 PM daily)
python main.py
```

---

## Gmail App Password Setup

Google requires an **App Password** (not your normal password) for SMTP:

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification**
3. Search for **"App Passwords"**
4. Select app → **Mail**, device → **Windows Computer**
5. Copy the 16-character password into `EMAIL_PASSWORD` in `.env`

---

## Excel / Contacts Format

Your `data/contacts.xlsx` must have these columns (column names are flexible):

| Email | Company | Name / ContactName | Title / Position | Sent | SentDate |
|---|---|---|---|---|---|
| hr@company.com | Acme Corp | Priya | HR Manager | | |

- **Sent** and **SentDate** are added automatically — don't fill them in.
- The service skips any row where `Sent = TRUE`.

---

## Cloud Deployment (Railway + Google Sheets)

Run the service 24/7 without keeping your PC on.

### Step 1 — Google Sheet setup

1. Create a new [Google Sheet](https://sheets.google.com)
2. Add columns: `Email | Company | ContactName | Position`
3. Paste your HR contacts into the sheet
4. Copy the **Sheet ID** from the URL:
   ```
   https://docs.google.com/spreadsheets/d/THIS_IS_THE_SHEET_ID/edit
   ```

### Step 2 — Google Service Account (free)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (e.g. "AutoMailer")
3. Enable **Google Sheets API** and **Google Drive API**
4. Go to **IAM & Admin → Service Accounts → Create**
5. Download the JSON key file
6. **Share your Google Sheet** with the service account email (ends in `@...gserviceaccount.com`) — give it **Editor** access

### Step 3 — Deploy to Railway

1. Push this repo to GitHub (contacts and .env are git-ignored — safe)
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select your repo
4. Go to **Variables** tab and add:

| Variable | Value |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `EMAIL_ADDRESS` | your Gmail |
| `EMAIL_PASSWORD` | your 16-char App Password |
| `GOOGLE_SHEET_ID` | the ID from Step 1 |
| `GOOGLE_CREDENTIALS_JSON` | paste the entire contents of the JSON key file |
| `START_HOUR` | `9` |
| `END_HOUR` | `16` |
| `EMAILS_PER_DAY` | `20` |

5. Railway will auto-deploy and start the scheduler. Done.

> **Resume:** Upload `resume.pdf` to Railway via the **Files** tab, or mount a Volume and set `RESUME_FILE` to that path.

---

## Commands

```bash
# Send 1 email immediately (test mode)
python main.py --now

# Send 5 emails immediately
python main.py --now --count 5

# Run full scheduler (9 AM – 4 PM loop)
python main.py
```

---

## How It Works

```
9:00 AM  → Checks Google Sheet / Excel for unsent contacts
9:00 AM  → Sends email #1, marks row as SENT
9:21 AM  → Sends email #2  (random 18–24 min gap)
9:44 AM  → Sends email #3
...
4:00 PM  → Stops. Sleeps until 9 AM tomorrow.
```

- Each email is personalized with `{contact_name}` and `{company}` from the sheet
- Resume PDF is attached automatically
- No contact is ever emailed twice (`Sent = TRUE` prevents duplicates)
- Service auto-stops when all contacts are exhausted

---

## Email Template

Edit `templates/email_template.txt`. The first line starting with `Subject:` becomes the email subject.

Available placeholders:
- `{contact_name}` — the HR person's name
- `{company}` — the company name

---

## Monitoring

```bash
# View today's log
type logs\email_automation_2024-05-07.log

# Count emails sent today
findstr "Email sent successfully" logs\email_automation_2024-05-07.log | find /c "sent"
```

---

## License

MIT
