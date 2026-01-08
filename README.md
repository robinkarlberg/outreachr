## Sponsor - Megadesk
<img width="50%" alt="pawelzmarlak-2026-01-08T15_11_47 724Z" src="https://github.com/user-attachments/assets/da7bbbe1-a71a-4932-9024-eeac43bde5b7" />

Increase conversions by 20% and cut support time in half with an intelligent chatbot.

**[Try Megadesk for free](https://getmegadesk.com/)** - perfect for indie devs like you and me :)

# Outreachr

Automated outreach email tool that scrapes websites to extract contact info and sends personalized emails.

Use it to send out cold emails in a few seconds when you find a potential website that would fit your product.

Also keeps track of what emails you have already sent to, as to not spam anyone.

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
EMAIL_REPLY_TO=your_reply_email@gmail.com
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
