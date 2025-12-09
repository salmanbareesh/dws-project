from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from rapidfuzz import fuzz, process

app = FastAPI()

EMAIL_REGEX = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
SOCIAL_PLATFORMS = ["facebook", "instagram", "linkedin", "youtube", "twitter", "x.com"]
HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_html(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return BeautifulSoup(r.text, "html.parser")
    except:
        pass
    return None


def extract_emails_socials(soup):
    if soup is None:
        return [], {}

    text = soup.get_text(" ")
    emails = set(re.findall(EMAIL_REGEX, text))

    # NEW: extract from mailto links
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()

        # extract from mailto:
        if href.startswith("mailto:"):
            email = href.replace("mailto:", "").split("?")[0]
            emails.add(email)

    socials = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        for platform in SOCIAL_PLATFORMS:
            if platform in href:
                socials.setdefault(platform, set()).add(href)

    return list(emails), {k: list(v) for k, v in socials.items()}



def get_internal_links(home_url, soup):
    domain = urlparse(home_url).netloc
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(home_url, a["href"])
        if domain in urlparse(href).netloc:
            links.append(href)
    return list(set(links))


def find_page(link_list, patterns):
    best = process.extractOne(patterns, link_list, scorer=fuzz.partial_ratio)
    if best and best[1] >= 60:
        return best[0]
    for link in link_list:
        for p in patterns:
            if p in link.lower():
                return link
    return None


def scrape_site(url):
    homepage_soup = get_html(url)
    if homepage_soup is None:
        return {"source": "error", "emails": [], "socials": {}}

    # FOOTER
    footer = homepage_soup.find("footer")
    if footer:
        emails, socials = extract_emails_socials(footer)
        if emails or socials:
            return {"source": "footer", "emails": emails, "socials": socials}

    # INTERNAL LINKS
    internal = get_internal_links(url, homepage_soup)

    # CONTACT PAGE
    contact_patterns = ["contact", "contact-us", "contactus", "support", "help", "get-in-touch"]
    contact_link = find_page(internal, contact_patterns)
    if contact_link:
        s = get_html(contact_link)
        emails, socials = extract_emails_socials(s)
        if emails or socials:
            return {"source": "contact_page", "page": contact_link, "emails": emails, "socials": socials}

    # ABOUT PAGE
    about_patterns = ["about", "about-us", "company", "who-we-are", "our-story"]
    about_link = find_page(internal, about_patterns)
    if about_link:
        s = get_html(about_link)
        emails, socials = extract_emails_socials(s)
        if emails or socials:
            return {"source": "about_page", "page": about_link, "emails": emails, "socials": socials}

    return {"source": "not_found", "emails": [], "socials": {}}


def run_scraper(domains):
    results = []
    for domain in domains:
        domain = domain.strip()
        if not domain:
            continue
        url = domain if domain.startswith("http") else f"https://{domain}"
        result = scrape_site(url)
        results.append({"domain": domain, **result})
    return results


# ---------------- API ENDPOINTS ----------------

# GET /api/scrape?domains=domain1.com,domain2.com
@app.get("/api/scrape")
def scrape_get(domains: str):
    domain_list = [d.strip() for d in domains.split(",") if d.strip()]
    results = run_scraper(domain_list)
    return JSONResponse(results)


# POST /api/scrape-bulk {"domains": ["domain1.com", "domain2.com"]}
@app.post("/api/scrape-bulk")
async def scrape_post(request: Request):
    data = await request.json()
    domains = data.get("domains", [])
    results = run_scraper(domains)
    return JSONResponse(results)
