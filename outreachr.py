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
        await browser.close()

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


async def main():
    parser = argparse.ArgumentParser(description='Outreach email automation tool')
    parser.add_argument('url', help='Website URL or domain to scrape')
    parser.add_argument('--template', help='Template file path', default='template.txt')

    args = parser.parse_args()

    # Ensure URL has protocol
    url = args.url
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # Scrape the website
    data = await scrape_website(url)

    # Check if we found any emails
    if not data['emails']:
        print("❌ No emails found on the website. Cannot send email.")
        return

    # Use the first email found
    recipient_email = data['emails'][0]

    if len(data['emails']) > 1:
        print(f"Found {len(data['emails'])} emails: {', '.join(data['emails'])}")
        print(f"Using: {recipient_email}")

    # Parse template
    email_subject, email_content = parse_template(args.template, data)

    print("\n" + "="*50)
    print("EMAIL PREVIEW")
    print("="*50)
    print(f"Subject: {email_subject}")
    print(f"To: {recipient_email}")
    print("-"*50)
    print(email_content)
    print("="*50 + "\n")

    # Ask for confirmation before sending
    confirmation = input("Send this email? (y/n): ").strip().lower()

    if confirmation == 'y' or confirmation == 'yes':
        # Send email
        params: resend.Emails.SendParams = {
            "from": EMAIL_FROM,
            "to": [recipient_email],
            "subject": email_subject,
            "text": email_content,
            "reply_to": [EMAIL_REPLY_TO],
        }

        email = resend.Emails.send(params)
        print(f"✓ Email sent! ID: {email}")
    else:
        print("Email not sent.")


if __name__ == '__main__':
    asyncio.run(main())