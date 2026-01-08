import dotenv
dotenv.load_dotenv()
import resend
import os
import asyncio
import argparse
import re
import json
from urllib.parse import urlparse
from pyppeteer import launch
from openai import OpenAI

resend.api_key = os.environ["RESEND_API_KEY"]
EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO", EMAIL_FROM)

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def extract_with_gpt(text, url):
    domain = urlparse(url).netloc

    prompt = f"""Analyze the following website content from {domain} and extract:
1. Company/Site Name - The official name of the company or website
2. Creator/Founder Name - The name of the founder, CEO, or main creator (if mentioned)
3. Contact Emails - Any contact email addresses found on the page

Website Content:
{text[:8000]}

Return your response as a JSON object with this exact format:
{{
    "company_name": "Company Name Here or null if not found",
    "creator_name": "Person Name or null if not found",
    "emails": ["email1@example.com", "email2@example.com"] or []
}}

Be precise and only extract information that is clearly stated. If something is not found, use null or empty array."""

    try:
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts structured information from website content. Always return valid JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            reasoning_effort="minimal"
        )

        result = json.loads(response.choices[0].message.content)

        # Fallback to domain name if no company name found
        if not result.get('company_name'):
            domain_parts = domain.replace('www.', '').split('.')
            result['company_name'] = domain_parts[0].capitalize() if domain_parts else None

        # Ensure emails is a list
        if not isinstance(result.get('emails'), list):
            result['emails'] = []

        print(f"GPT extracted: {result}")
        return result

    except Exception as e:
        print(f"Error using GPT for extraction: {e}")
        # Fallback to domain name
        domain_parts = domain.replace('www.', '').split('.')
        return {
            'company_name': domain_parts[0].capitalize() if domain_parts else None,
            'creator_name': None,
            'emails': []
        }


async def scrape_website(url):
    """Scrape website and extract relevant information using GPT."""
    print(f"Visiting {url}...")

    browser = await launch(headless=True, args=['--no-sandbox'])
    page = await browser.newPage()

    try:
        await page.goto(url, {'waitUntil': 'networkidle2', 'timeout': 30000})

        # Get page content including all hrefs (which may contain mailto: links)
        text = await page.evaluate('''() => {
            const bodyText = document.body.innerText;
            const links = Array.from(document.querySelectorAll('a[href]'));
            const hrefs = links.map(link => link.href).join('\\n');
            return bodyText + '\\n\\nLinks found on page:\\n' + hrefs;
        }''')

        # Use GPT to extract information
        print("Extracting information...")
        extracted = extract_with_gpt(text, url)

        result = {
            'emails': extracted['emails'],
            'company_name': extracted['company_name'],
            'creator_name': extracted['creator_name'],
            'url': url,
            'site_name': extracted['company_name']  # Use company_name as site_name
        }

    finally:
        # Close page before closing browser to avoid cleanup errors
        await page.close()
        await browser.close()
        # Give browser time to cleanup
        await asyncio.sleep(0.1)

    return result


def parse_template(template_path, data):
    """Parse template file and replace variables with data or defaults.

    Returns:
        tuple: (subject, body) where subject is the first line and body is the rest
    """
    with open(template_path, 'r') as f:
        template = f.read()

    # Split into subject (first line) and body (rest)
    lines = template.split('\n', 1)
    subject = lines[0] if lines else ''
    body = lines[1] if len(lines) > 1 else ''

    # Find all template variables in format {{variable}} or {{variable:default}}
    pattern = r'\{\{(\w+)(?::([^}]+))?\}\}'

    def replace_var(match):
        var_name = match.group(1)
        default_value = match.group(2) if match.group(2) else ''

        # Get value from data or use default
        value = data.get(var_name, default_value)
        return str(value) if value else default_value

    subject_result = re.sub(pattern, replace_var, subject)
    body_result = re.sub(pattern, replace_var, body)

    return subject_result, body_result


async def process_url(url, template_path, override_email, auto_accept, sent_emails_history, session_sent_emails):
    """Process a single URL: scrape, generate email, and send."""
    # Ensure URL has protocol
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Scrape the website
    data = await scrape_website(url)

    # Determine recipient email
    if override_email:
        # Use manually provided email
        recipient_email = override_email
        print(f"Using provided email: {recipient_email}")
    else:
        # Check if we found any emails
        if not data['emails']:
            print("No emails found on the website. Cannot send email.")
            return

        # Use the first email found
        recipient_email = data['emails'][0]

        if len(data['emails']) > 1:
            print(f"Found {len(data['emails'])} emails: {', '.join(data['emails'])}")
            print(f"Using: {recipient_email}")

    # Parse template
    email_subject, email_content = parse_template(template_path, data)

    print("\n" + "="*50)
    print("EMAIL PREVIEW")
    print("="*50)
    print(f"Subject: {email_subject}")
    print(f"To: {recipient_email}")
    print("-"*50)
    print(email_content)
    print("="*50 + "\n")

    # Check if already sent in this session
    if recipient_email in session_sent_emails:
        print(f"⚠️  Already sent to {recipient_email} in this session. Skipping.")
        return

    # Check if recipient_email is in historical sent emails
    already_sent = False
    for email_record in sent_emails_history:
        # Get the 'to' field - it's a list of email addresses
        to_emails = email_record.get('to', []) if isinstance(email_record, dict) else getattr(email_record, 'to', [])

        if recipient_email in to_emails:
            already_sent = True
            subject = email_record.get('subject') if isinstance(email_record, dict) else getattr(email_record, 'subject', 'No subject')
            created_at = email_record.get('created_at') if isinstance(email_record, dict) else getattr(email_record, 'created_at', 'Unknown date')
            last_event = email_record.get('last_event') if isinstance(email_record, dict) else getattr(email_record, 'last_event', 'Unknown')

            print(f"\n⚠️  WARNING: You already sent an email to {recipient_email}")
            print(f"   Previous email: \"{subject}\"")
            print(f"   Sent on: {created_at}")
            print(f"   Status: {last_event}")
            break

    if already_sent:
        if not auto_accept:
            skip = input("\nSkip sending to avoid duplicate? (y/n): ").strip().lower()
            if skip in ('y', 'yes'):
                print("Skipped sending duplicate email.")
                return
            else:
                print("Proceeding to send anyway...")
        else:
            print("Skipped sending duplicate email.")
            return

    # Ask for confirmation before sending (unless auto-accept is enabled)
    should_send = auto_accept
    if not auto_accept:
        confirmation = input("Send this email? (y/n): ").strip().lower()
        should_send = confirmation in ('y', 'yes')

    if should_send:
        params: resend.Emails.SendParams = {
            "from": EMAIL_FROM,
            "to": [recipient_email],
            "subject": email_subject,
            "text": email_content,
            "reply_to": [EMAIL_REPLY_TO],
        }

        email = resend.Emails.send(params)
        print(f"✓ Email sent! ID: {email}")

        # Add to session sent list
        session_sent_emails.add(recipient_email)
    else:
        print("Email not sent.")


async def main():
    parser = argparse.ArgumentParser(description='Outreach email automation tool')
    parser.add_argument('urls', nargs='+', help='Website URL(s) or domain(s) to scrape')
    parser.add_argument('--template', help='Template file path', default='template.txt')
    parser.add_argument('--to', help='Override recipient email address', dest='recipient_email')
    parser.add_argument('-y', '--yes', action='store_true', help='Auto-accept all prompts without confirmation')

    args = parser.parse_args()

    # Fetch sent emails history once at startup
    print("Fetching email history from Resend...")
    sent_emails_history = []
    try:
        resp = resend.Emails.list()
        # Handle response - it could be a dict or an object
        if isinstance(resp, dict):
            sent_emails_history = resp.get('data', [])
        else:
            sent_emails_history = resp.data if hasattr(resp, 'data') else []
        print(f"Found {len(sent_emails_history)} previously sent emails.\n")
    except Exception as e:
        print(f"Warning: Could not fetch email history: {e}")
        print("Continuing without duplicate check...\n")

    # Track emails sent in this session
    session_sent_emails = set()

    # Process each URL
    for i, url in enumerate(args.urls):
        if len(args.urls) > 1:
            print(f"\n{'='*60}")
            print(f"Processing site {i+1}/{len(args.urls)}: {url}")
            print(f"{'='*60}\n")

        await process_url(url, args.template, args.recipient_email, args.yes, sent_emails_history, session_sent_emails)

        # Add spacing between multiple sites
        if i < len(args.urls) - 1:
            print("\n" + "-"*60 + "\n")


if __name__ == '__main__':
    asyncio.run(main())