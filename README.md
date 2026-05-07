# Email Automation Service

A professional, secure Python-based email automation service designed for job applications. It sends personalized emails with resume attachments to HR contacts at a controlled rate (e.g., 20 per day) with random intervals to ensure high deliverability and avoid spam filters.

Supports both **local Excel** files and **Google Sheets** (Cloud) as the contact database.

---

## Key Features

- **Automated Scheduling:** Runs between business hours (9 AM - 4 PM) and sleeps outside this window.
- **Randomized Intervals:** Waits 18-24 minutes between emails to mimic human behavior.
- **Smart Personalization:** Auto-fills `{contact_name}` and `{company}` in templates.
- **Duplicate Prevention:** Automatically marks contacts as "SENT" in the database to ensure no one is contacted twice.
- **Cloud Ready:** Optimized for deployment on Railway or Render using Google Sheets.

---

## Quick Start (Local)

```bash
# 1. Clone and install
git clone <your-repo>
cd AutoMailer
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env - add your Gmail address and App Password

# 3. Add your files
# Place contacts.xlsx in data/
# Place resume.pdf in data/

# 4. Test - send 1 email immediately
python main.py --now

# 5. Run the full scheduler (9 AM - 4 PM daily loop)
python main.py
```

---

## Gmail App Password Setup

Google requires an **App Password** (not your normal password) for SMTP:

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification**
3. Search for **"App Passwords"**
4. Select app -> **Mail**, device -> **Other (Custom Name)** (e.g., "AutoMailer")
5. Copy the 16-character password into `EMAIL_PASSWORD` in `.env`

---

## Cloud Deployment (Railway + Google Sheets)

### Step 1 - Google Sheet Setup
1. Create a [Google Sheet](https://sheets.google.com).
2. Add headers: `Email`, `Company`, `ContactName`, `Position`.
3. Copy the **Sheet ID** from the URL: `.../d/THIS_IS_THE_ID/edit`.

### Step 2 - Google Service Account
1. Go to [Google Cloud Console](https://console.cloud.google.com).
2. Enable **Google Sheets API** and **Google Drive API**.
3. Create a **Service Account** and download the **JSON Key**.
4. **Share your Google Sheet** with the Service Account email as an **Editor**.

### Step 3 - Deployment Variables
When deploying to Railway, add these Environment Variables:

| Variable | Tip |
|---|---|
| `GOOGLE_SHEET_ID` | The ID from Step 1 |
| `GOOGLE_CREDENTIALS_JSON` | The entire JSON key file content |

> **IMPORTANT:** In your `.env` file, wrap the `GOOGLE_CREDENTIALS_JSON` value in single quotes to handle special characters:
> `GOOGLE_CREDENTIALS_JSON='{"type": "service_account", ...}'`

---

## How It Works (The Loop)

Once the service is started (locally or on a server), it follows this logic:

- **Check Time:** If it's before 9 AM, it sleeps until 9 AM. If it's after 4 PM, it sleeps until 9 AM the next day.
- **Send Cycle:**
  1. Pick the next contact where `Sent` is not `TRUE`.
  2. Send the personalized email + resume.
  3. Mark the row as `TRUE` in the sheet/Excel.
  4. Wait for a random interval (e.g., 21 minutes).
  5. Repeat until 20 emails are sent or 4 PM is reached.
- **Next Day:** If the daily limit (20) is reached, it sleeps until 9 AM the next morning and starts again.

**Yes, once deployed, it stays active and will automatically resume every morning at your configured `START_HOUR`.**

---

## Monitoring

- **Logs:** Check the `logs/` directory for detailed execution history.
- **Tracking:** The `Sent` and `SentDate` columns in your sheet/Excel will update in real-time.

---

## License
MIT
