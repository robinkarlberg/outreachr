# Outreachr

Automated outreach email tool that scrapes websites to extract contact info and sends personalized emails.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file with: (see `.env.example`)
```
OPENAI_API_KEY=your_openai_key
RESEND_API_KEY=your_resend_key
EMAIL_FROM=your_email@domain.com
```

## Usage

```bash
python outreachr.py <website-url>
```

The script will:
1. Visit the website with pyppeteer
2. Extract company name, creator name, and emails using GPT-5-mini
3. Fill in the template with extracted data
4. Show preview and ask for confirmation before sending

## Template Format

First line = email subject
Rest = email body

Variables: `{{variable:default_value}}`

Example:
```
Hey {{creator_name:there}}!
Quick question about {{site_name:your site}}...
```

If a value is found, it replaces the variable. Otherwise, uses the default after the colon.