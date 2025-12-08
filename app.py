from fastapi import FastAPI
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
    emails = list(set(re.findall(EMAIL_REGEX, text)))

    socials = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        for platform in SOCIAL_PLATFORMS:
            if platform in href:
                socials.setdefault(platform, set()).add(href)
    return emails, {k: list(v) for k, v in socials.items()}


def get_internal_links(home_url, soup):
    domain = urlparse(home_url).netloc
    links = []

    for a in soup.find_all("a", href=True):
        href = urljoin(home_url, a["href"])
        if domain in urlparse(href).netloc:
            links.append(href)

    return list(set(links))


def fuzzy_find_page(links, keywords, threshold=60):
    ranked = process.extract(keywords, links, scorer=fuzz.partial_ratio, limit=5)
    for keyword, link, score in ranked:
        if score >= threshold:
            return link
    return None


def scrape_site(url):
    homepage_soup = get_html(url)
    if homepage_soup is None:
        return {"source": "error", "emails": [], "socials": {}}

    footer = homepage_soup.find("footer")
    if footer:
        emails, socials = extract_emails_socials(footer)
        if emails or socials:
            return {"source": "footer", "emails": emails, "socials": socials}

    internal_links = get_internal_links(url, homepage_soup)

    contact_link = fuzzy_find_page(internal_links, ["contact", "support"])
    if contact_link:
        s = get_html(contact_link)
        emails, socials = extract_emails_socials(s)
        if emails or socials:
            return {"source": "contact_page", "page": contact_link, "emails": emails, "socials": socials}

    about_link = fuzzy_find_page(internal_links, ["about", "company"])
    if about_link:
        s = get_html(about_link)
        emails, socials = extract_emails_socials(s)
        if emails or socials:
            return {"source": "about_page", "page": about_link, "emails": emails, "socials": socials}

    return {"source": "not_found", "emails": [], "socials": {}}


@app.get("/api/scrape")
def scrape(domain: str):
    if not domain.startswith("http"):
        domain = "https://" + domain
    return JSONResponse(scrape_site(domain))
