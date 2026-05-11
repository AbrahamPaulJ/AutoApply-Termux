# AutoApply-Termux

Auto-apply to **Quick Apply** job listings on [seek.com.au](https://www.seek.com.au) — running natively on Android via Termux, with no PC required.

A Selenium port of [AutoApply](https://github.com/AbrahamPaulJ/AutoApply), rebuilt to run on Android using Firefox + Geckodriver instead of Playwright + Chromium.

---

## Features

- Scrapes Seek job listings using your saved filters
- Detects Quick Apply vs Standard Apply listings
- Skips already-processed job IDs across runs
- Filters by posting timeframe (e.g. last hour)
- Gemini AI suitability check against your resume and personal constraints
- Generates a tailored resume PDF per job via jsoncv + Chromium
- Generates a tailored cover letter via Gemini
- Answers recruiter questions dynamically via Gemini
- Submits the application automatically
- Sends Telegram notifications for suitability results and successful applications

---

## Stack

- **Termux** (F-Droid/GitHub version) — Linux environment on Android
- **Termux:X11** — X display server for headed browser
- **Firefox + Geckodriver** — browser automation
- **Selenium 4.x** — Python automation framework
- **jsoncv** — resume HTML builder (Vite-based)
- **Chromium** — headless PDF generation
- **Gemini API** — suitability, resume tailoring, cover letter, Q&A
- **Telegram Bot API** — real-time notifications

---

## Requirements

- Android phone with [Termux](https://github.com/termux/termux-app/releases) (F-Droid or GitHub APK — **not Google Play**)
- [Termux:X11](https://github.com/termux/termux-x11/releases) APK installed
- Gemini API key (free at [aistudio.google.com](https://aistudio.google.com/app/apikey))
- Telegram Bot token (via [@BotFather](https://t.me/BotFather))
- Seek account with email/password login

---

## Installation

### 1. Termux packages

```bash
pkg update && pkg upgrade -y
pkg install python git openssh -y
pkg install x11-repo -y
pkg install firefox geckodriver chromium termux-x11-nightly -y
pip install selenium pyyaml
```

### 2. Clone repo

```bash
git clone https://github.com/AbrahamPaulJ/AutoApply-Termux.git
cd AutoApply-Termux
```

### 3. Install jsoncv dependencies

```bash
cd jsoncv
npm install
cd ..
```

### 4. Set up user profile

```bash
mkdir -p Users/abraham/mycv
cp Users/abraham/resume.example.json Users/abraham/resume.txt
# Edit resume.txt with your details in JSON Resume format
# Edit Users/abraham/info.yaml with your config
```

### 5. Set up Gemini and Telegram in `gemini.py`

```python
GEMINI_API_KEY = "your-key-here"
BOT_TOKEN = "your-telegram-bot-token"
```

### 6. Save Seek login session

```bash
export DISPLAY=:0
termux-x11 :0 &
python seek_login.py
```

Log in manually in the X11 window using email/password (not Google), then press Enter to save the session.

---

## Usage

### Launch X11

```bash
termux-x11 :0 &
export DISPLAY=:0
```

### Run scraper

```bash
cd AutoApply-Termux

# Full production run
python mvp_scraper.py --submit

# Test apply flow on first Quick Apply job, no submit
python mvp_scraper.py --force-apply --limit 1 --clear-ids

# Skip Gemini entirely (test form flow only)
python mvp_scraper.py --no-gemini --force-apply --limit 1 --clear-ids

# Real timeframe filter (jobs posted in last few hours only)
python mvp_scraper.py --submit --timeframe "^\d+[mh]$"

# Debug recruiter questions
python mvp_scraper.py --force-apply --limit 1 --clear-ids --debug-form
```

### Run continuously (every 30 mins)

```bash
pkg install termux-api
termux-wake-lock

while true; do
    python mvp_scraper.py --submit --timeframe "^\d+[mh]$"
    sleep 1800
done
```

---

## User Config (`Users/abraham/info.yaml`)

```yaml
name: "Your Name"
email: "you@email.com"
phone: "04xx xxx xxx"
address: "Your Address"
chat_id: "your-telegram-chat-id"
filter: "https://www.seek.com.au/jobs/..."  # Your Seek search URL with filters

additional_info: |
  - Visa: ...
  - Work rights: ...
  - Driver's license: No
  - etc.

suitable_prompt: |
  ... (see example)

cover_letter_prompt: |
  ... (see example)

resume_prompt: |
  ... (see example)
```

---

## Folder Structure

```
AutoApply-Termux/
├── mvp_scraper.py          # Main scraper and apply logic
├── gemini.py               # Gemini API calls (gitignored — add your own)
├── utils.py                # Helper functions
├── seek_login.py           # One-time login session saver
├── jsoncv/                 # Resume HTML builder
│   ├── cv.json             # Sample CV
│   └── ...
└── Users/
    └── abraham/
        ├── resume.txt      # Your resume in JSON Resume format
        ├── info.yaml       # Your config and prompts
        └── mycv/           # Generated PDFs (gitignored)
```

---

## Notes

- Termux must be installed from **F-Droid or GitHub**, not Google Play
- Seek login must use **email/password**, not Google OAuth (bot detection)
- `gemini.py` is gitignored — create your own with your API key
- `Users/` folder is gitignored — never commit your personal data
- Disable battery optimization for Termux in Android settings for background running

---

## Differences from Original AutoApply (PC version)

| Feature | Original (PC) | This (Android) |
|---|---|---|
| Browser | Playwright + Chromium | Selenium + Firefox |
| PDF generation | Playwright `page.pdf()` | Chromium headless CLI |
| Platform | Windows/Mac/Linux | Android (Termux) |
| Chrome profile | `chrome_profile/` folder | Firefox persistent profile |
| Run trigger | `.bat` script | Termux widget / loop |
| Async | Yes (`asyncio`) | No (synchronous) |
