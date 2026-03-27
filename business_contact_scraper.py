#!/usr/bin/env python3
"""
Business Contact Scraper
========================
Scrapes websites to extract: email, phone, Instagram, Facebook handles.

Usage:
    python3 business_contact_scraper.py input.csv
    python3 business_contact_scraper.py input.xlsx

Input file must have a column named 'website' (or 'url' or 'Website' or 'URL').
Optionally include a 'name' or 'business' column for identification.

Output: business_contacts_output.csv
"""

import csv
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ── Configuration ────────────────────────────────────────────────────────────

TIMEOUT = 15  # seconds per request
MAX_WORKERS = 10  # parallel requests
RETRY_COUNT = 2
DELAY_BETWEEN = 0.5  # seconds between requests (politeness)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ── Regex Patterns ───────────────────────────────────────────────────────────

EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

PHONE_PATTERN = re.compile(
    r"""
    (?:
        (?:\+?\d{1,3}[\s\-.]?)?        # country code
        (?:\(?\d{2,4}\)?[\s\-.]?)?      # area code
        \d{3,4}[\s\-.]?\d{3,4}         # main number
    )
    """,
    re.VERBOSE,
)

# More targeted phone pattern to reduce false positives
PHONE_STRICT = re.compile(
    r"(?:(?:\+|00)\d{1,3}[\s\-.]?)?\(?\d{2,5}\)?[\s\-.]?\d{3,4}[\s\-.]?\d{3,4}\b"
)

INSTAGRAM_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)/?",
    re.IGNORECASE,
)

FACEBOOK_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.|m\.|web\.)?facebook\.com/([a-zA-Z0-9_.]+)/?",
    re.IGNORECASE,
)

# Emails to exclude (common false positives)
EXCLUDED_EMAIL_DOMAINS = {
    "example.com", "sentry.io", "wixpress.com", "w3.org",
    "schema.org", "googleapis.com", "googletagmanager.com",
    "facebook.com", "apple.com", "microsoft.com",
}

EXCLUDED_EMAIL_PREFIXES = {
    "noreply", "no-reply", "mailer-daemon", "postmaster",
}


# ── Helper Functions ─────────────────────────────────────────────────────────

def normalize_url(url: str) -> str:
    """Ensure URL has a scheme."""
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def fetch_page(url: str) -> str | None:
    """Fetch HTML content of a page with retries."""
    for attempt in range(RETRY_COUNT):
        try:
            resp = requests.get(
                url, headers=HEADERS, timeout=TIMEOUT,
                allow_redirects=True, verify=False,
            )
            resp.raise_for_status()
            return resp.text
        except Exception:
            if attempt < RETRY_COUNT - 1:
                time.sleep(1)
    return None


def extract_emails(soup: BeautifulSoup, html: str) -> list[str]:
    """Extract email addresses from HTML."""
    emails = set()

    # From mailto: links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "mailto:" in href:
            email = href.split("mailto:")[-1].split("?")[0].strip()
            if email:
                emails.add(email.lower())

    # From page text using regex
    text = soup.get_text(separator=" ")
    for match in EMAIL_PATTERN.findall(text):
        emails.add(match.lower())

    # From raw HTML (catches emails in data attributes, meta tags, etc.)
    for match in EMAIL_PATTERN.findall(html):
        emails.add(match.lower())

    # Filter out junk
    filtered = []
    for email in emails:
        domain = email.split("@")[-1]
        prefix = email.split("@")[0]
        if domain in EXCLUDED_EMAIL_DOMAINS:
            continue
        if prefix in EXCLUDED_EMAIL_PREFIXES:
            continue
        if domain.endswith((".png", ".jpg", ".gif", ".svg", ".css", ".js")):
            continue
        if len(email) > 60:
            continue
        filtered.append(email)

    return sorted(filtered)


def extract_phones(soup: BeautifulSoup, html: str) -> list[str]:
    """Extract phone numbers from HTML."""
    phones = set()

    # From tel: links (most reliable)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "tel:" in href:
            phone = href.split("tel:")[-1].strip()
            phone = urllib.parse.unquote(phone)
            if phone:
                phones.add(phone)

    # From text near phone-related keywords
    text = soup.get_text(separator=" ")
    for match in PHONE_STRICT.findall(text):
        clean = match.strip()
        # Must have at least 7 digits to be a phone number
        digits = re.sub(r"\D", "", clean)
        if 7 <= len(digits) <= 15:
            phones.add(clean)

    # From raw HTML (meta tags, structured data)
    phone_meta_patterns = [
        r'"telephone"\s*:\s*"([^"]+)"',
        r'"phone"\s*:\s*"([^"]+)"',
        r'content="(\+?[\d\s\-().]{7,20})"',
    ]
    for pattern in phone_meta_patterns:
        for match in re.findall(pattern, html, re.IGNORECASE):
            digits = re.sub(r"\D", "", match)
            if 7 <= len(digits) <= 15:
                phones.add(match.strip())

    return sorted(phones)


def extract_social(soup: BeautifulSoup, html: str, pattern: re.Pattern, platform: str) -> list[str]:
    """Extract social media handles from links."""
    handles = set()
    excluded_paths = {
        "sharer", "share", "dialog", "plugins", "login",
        "pages", "groups", "events", "help", "privacy",
        "policy", "terms", "about", "settings", "hashtag",
        "tr", "flx", "watch", "reel", "reels", "stories",
    }

    # From <a> tags
    for a in soup.find_all("a", href=True):
        href = a["href"]
        match = pattern.search(href)
        if match:
            handle = match.group(1).rstrip("/").split("?")[0].split("#")[0]
            if handle.lower() not in excluded_paths and len(handle) > 1:
                handles.add(handle)

    # From raw HTML (catches dynamically loaded links, data attributes)
    for match in pattern.findall(html):
        handle = match.rstrip("/").split("?")[0].split("#")[0]
        if handle.lower() not in excluded_paths and len(handle) > 1:
            handles.add(handle)

    return sorted(handles)


def find_contact_pages(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Find links to contact/about pages that might have more info."""
    contact_keywords = {"contact", "about", "connect", "reach", "get-in-touch"}
    pages = []

    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        text = (a.get_text() or "").lower().strip()

        if any(kw in href or kw in text for kw in contact_keywords):
            full_url = urllib.parse.urljoin(base_url, a["href"])
            # Only follow links on the same domain
            if urllib.parse.urlparse(base_url).netloc in full_url:
                pages.append(full_url)

    return list(set(pages))[:3]  # Max 3 contact pages


def scrape_business(name: str, url: str) -> dict:
    """Scrape a single business website for contact info."""
    result = {
        "business_name": name,
        "website": url,
        "emails": "",
        "phones": "",
        "instagram": "",
        "facebook": "",
        "status": "",
    }

    url = normalize_url(url)
    if not url:
        result["status"] = "No URL provided"
        return result

    # Fetch main page
    html = fetch_page(url)
    if not html:
        result["status"] = "Failed to fetch"
        return result

    soup = BeautifulSoup(html, "lxml")

    all_emails = extract_emails(soup, html)
    all_phones = extract_phones(soup, html)
    all_ig = extract_social(soup, html, INSTAGRAM_PATTERN, "instagram")
    all_fb = extract_social(soup, html, FACEBOOK_PATTERN, "facebook")

    # Also check contact/about pages for more data
    contact_pages = find_contact_pages(soup, url)
    for page_url in contact_pages:
        time.sleep(DELAY_BETWEEN)
        page_html = fetch_page(page_url)
        if page_html:
            page_soup = BeautifulSoup(page_html, "lxml")
            all_emails.extend(extract_emails(page_soup, page_html))
            all_phones.extend(extract_phones(page_soup, page_html))
            all_ig.extend(extract_social(page_soup, page_html, INSTAGRAM_PATTERN, "instagram"))
            all_fb.extend(extract_social(page_soup, page_html, FACEBOOK_PATTERN, "facebook"))

    # Deduplicate
    result["emails"] = " | ".join(sorted(set(all_emails)))
    result["phones"] = " | ".join(sorted(set(all_phones)))
    result["instagram"] = " | ".join(sorted(set(all_ig)))
    result["facebook"] = " | ".join(sorted(set(all_fb)))
    result["status"] = "OK"

    return result


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 business_contact_scraper.py <input_file.csv|xlsx>")
        print("\nInput file must have a 'website' (or 'url') column.")
        print("Optionally include a 'name' (or 'business') column.")
        sys.exit(1)

    input_file = sys.argv[1]

    # Read input file
    if input_file.endswith(".xlsx"):
        df = pd.read_excel(input_file)
    else:
        df = pd.read_csv(input_file)

    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]

    # Find the URL column
    url_col = None
    for col in ["website", "url", "site", "web", "link"]:
        if col in df.columns:
            url_col = col
            break
    if url_col is None:
        print(f"Error: No 'website' or 'url' column found. Columns: {list(df.columns)}")
        sys.exit(1)

    # Find the name column
    name_col = None
    for col in ["name", "business", "company", "business_name", "company_name"]:
        if col in df.columns:
            name_col = col
            break

    businesses = []
    for _, row in df.iterrows():
        name = str(row[name_col]).strip() if name_col else ""
        url = str(row[url_col]).strip()
        if url and url.lower() != "nan":
            businesses.append((name, url))

    print(f"Found {len(businesses)} businesses to scrape.")
    print(f"Using {MAX_WORKERS} parallel workers...\n")

    results = []
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(scrape_business, name, url): (name, url)
            for name, url in businesses
        }

        for future in as_completed(futures):
            name, url = futures[future]
            completed += 1
            try:
                result = future.result()
                results.append(result)
                status = result["status"]
                found = []
                if result["emails"]:
                    found.append(f"emails:{len(result['emails'].split('|'))}")
                if result["phones"]:
                    found.append(f"phones:{len(result['phones'].split('|'))}")
                if result["instagram"]:
                    found.append("IG")
                if result["facebook"]:
                    found.append("FB")
                info = ", ".join(found) if found else "no data"
                print(f"[{completed}/{len(businesses)}] {name or url[:40]} - {status} ({info})")
            except Exception as e:
                print(f"[{completed}/{len(businesses)}] {name or url[:40]} - Error: {e}")
                results.append({
                    "business_name": name,
                    "website": url,
                    "emails": "",
                    "phones": "",
                    "instagram": "",
                    "facebook": "",
                    "status": f"Error: {e}",
                })

    # Save output
    output_file = "business_contacts_output.csv"
    out_df = pd.DataFrame(results)
    out_df = out_df[["business_name", "website", "emails", "phones", "instagram", "facebook", "status"]]
    out_df.to_csv(output_file, index=False)

    # Print summary
    ok_count = sum(1 for r in results if r["status"] == "OK")
    email_count = sum(1 for r in results if r["emails"])
    phone_count = sum(1 for r in results if r["phones"])
    ig_count = sum(1 for r in results if r["instagram"])
    fb_count = sum(1 for r in results if r["facebook"])

    print(f"\n{'='*50}")
    print(f"DONE! Results saved to: {output_file}")
    print(f"{'='*50}")
    print(f"Total businesses:  {len(businesses)}")
    print(f"Successfully scraped: {ok_count}")
    print(f"With emails:       {email_count}")
    print(f"With phones:       {phone_count}")
    print(f"With Instagram:    {ig_count}")
    print(f"With Facebook:     {fb_count}")


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    main()
