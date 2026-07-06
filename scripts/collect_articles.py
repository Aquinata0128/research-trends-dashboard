import csv
import json
import re
import time
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

import feedparser
import requests


# Project folders
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

JOURNALS_FILE = DATA_DIR / "journals.csv"
PAPERS_FILE = DATA_DIR / "papers.json"


# First real RSS collection targets.
RSS_FEEDS = [
    {
        "journal_name": "Public Understanding of Science",
        "grade": "A",
        "feed_url": "https://journals.sagepub.com/action/showFeed?ai=2b4&feed=rss&jc=pus&mi=ehikzz&type=etoc&ui=0"
    },
    {
        "journal_name": "Science Communication",
        "grade": "A",
        "feed_url": "https://journals.sagepub.com/action/showFeed?ai=2b4&feed=rss&jc=scx&mi=ehikzz&type=etoc&ui=0"
    },
    {
        "journal_name": "Social Studies of Science",
        "grade": "A",
        "feed_url": "https://journals.sagepub.com/action/showFeed?ai=2b4&feed=rss&jc=sss&mi=ehikzz&type=etoc&ui=0"
    },
    {
        "journal_name": "Science, Technology, & Human Values",
        "grade": "A",
        "feed_url": "https://journals.sagepub.com/action/showFeed?ai=2b4&feed=rss&jc=sth&mi=ehikzz&type=etoc&ui=0"
    }
]


KEYWORDS = [
    "science uncertainty",
    "scientific uncertainty",
    "science communication",
    "public understanding of science",
    "science and technology studies",
    "STS",
    "politicization of science",
    "science politicization",
    "climate change",
    "climate crisis",
    "environmental communication",
    "sustainability",
    "ecosystem",
    "ESG",
    "carbon market",
    "carbon markets",
    "biodiversity",
    "valuation",
    "environmental valuation",
    "opinion-based polarization",
    "polarization",
    "politicization",
    "colonialism",
    "decolonial",
    "postcolonial",
    "Global South",
    "environmental justice",
    "climate justice",
    "public perception",
    "public engagement",
    "trust",
    "expertise",
    "responsibility",
    "risk communication",
    "policy support"
]


CROSSREF_API_BASE = "https://api.crossref.org/works"

# Optional but recommended by Crossref etiquette.
# Later you can replace this with your email if you want.
CROSSREF_HEADERS = {
    "User-Agent": "ResearchTrendsDashboard/0.1 (mailto:example@example.com)"
}


def load_journals():
    """
    Read the journal list from data/journals.csv.
    This is kept for later expansion.
    """
    journals = []

    with open(JOURNALS_FILE, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            journals.append(row)

    return journals


def clean_text(text):
    """
    Clean simple HTML tags, HTML entities, and extra spaces from RSS or Crossref text.
    """
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_abstract(abstract, journal_name):
    """
    Remove journal metadata that sometimes appears before the actual abstract.
    """
    if not abstract:
        return ""

    abstract = clean_text(abstract)

    patterns_to_remove = [
        rf"^{re.escape(journal_name)},\s*Ahead of Print\.?\s*",
        rf"^{re.escape(journal_name)},\s*OnlineFirst\.?\s*",
        rf"^{re.escape(journal_name)}\s*",
        r"^Ahead of Print\.?\s*",
        r"^OnlineFirst\.?\s*"
    ]

    for pattern in patterns_to_remove:
        abstract = re.sub(pattern, "", abstract, flags=re.IGNORECASE)

    return abstract.strip()


def clean_author_name(author_name):
    """
    Clean author strings from RSS feeds.
    """
    if not author_name:
        return ""

    author_name = clean_text(author_name)

    # Remove long numeric IDs and anything after them.
    author_name = re.sub(r"\d{4,}.*$", "", author_name).strip()

    affiliation_markers = [
        "University",
        "Institute",
        "Department",
        "School",
        "College",
        "Faculty",
        "Centre",
        "Center",
        "Laboratory",
        "Max Planck",
        "Germany",
        "USA",
        "United Kingdom"
    ]

    for marker in affiliation_markers:
        pattern = rf"\b{re.escape(marker)}\b.*$"
        author_name = re.sub(pattern, "", author_name).strip(" ,;")

    return author_name.strip()


def clean_author_list(authors):
    """
    Clean a list of author names and remove empty values.
    """
    cleaned_authors = []

    for author in authors:
        cleaned_author = clean_author_name(author)

        if cleaned_author:
            cleaned_authors.append(cleaned_author)

    return cleaned_authors


def find_keyword_matches(title, abstract):
    """
    Find interest keywords in the article title and abstract.
    Matching is case-insensitive.
    """
    combined_text = f"{title} {abstract}".lower()
    matches = []

    for keyword in KEYWORDS:
        if keyword.lower() in combined_text:
            matches.append(keyword)

    return matches


def get_authors_from_rss(entry):
    """
    Extract authors from an RSS entry.
    """
    authors = []

    if "authors" in entry:
        for author in entry.authors:
            if "name" in author:
                authors.append(author.name)

    if not authors and "author" in entry:
        authors.append(entry.author)

    if not authors and "dc_creator" in entry:
        authors.append(entry.dc_creator)

    return clean_author_list(authors)


def get_authors_from_crossref(item):
    """
    Extract clean author names from Crossref metadata.
    """
    authors = []

    for author in item.get("author", []):
        given = author.get("given", "")
        family = author.get("family", "")
        full_name = f"{given} {family}".strip()

        if full_name:
            authors.append(full_name)

    return authors


def get_publication_date_from_rss(entry):
    """
    Extract raw publication date from RSS entry.
    """
    if "published" in entry:
        return entry.published

    if "updated" in entry:
        return entry.updated

    return ""


def clean_publication_date(publication_date):
    """
    Convert RSS date strings to YYYY-MM-DD when possible.
    """
    if not publication_date:
        return ""

    try:
        parsed_date = parsedate_to_datetime(publication_date)
        return parsed_date.date().isoformat()
    except Exception:
        pass

    match = re.search(r"\d{4}-\d{2}-\d{2}", publication_date)
    if match:
        return match.group(0)

    year_match = re.search(r"\d{4}", publication_date)
    if year_match:
        return year_match.group(0)

    return ""


def get_date_parts_from_crossref(date_object):
    """
    Crossref dates often look like:
    {'date-parts': [[2026, 7, 1]]}
    """
    if not date_object:
        return ""

    date_parts = date_object.get("date-parts", [])

    if not date_parts or not date_parts[0]:
        return ""

    parts = date_parts[0]

    year = parts[0]
    month = parts[1] if len(parts) > 1 else 1
    day = parts[2] if len(parts) > 2 else 1

    return f"{year:04d}-{month:02d}-{day:02d}"


def choose_crossref_publication_date(item):
    """
    Choose the most useful publication date from Crossref metadata.
    """
    for field in ["published-online", "published-print", "published", "issued"]:
        if field in item:
            clean_date = get_date_parts_from_crossref(item[field])

            if clean_date:
                return clean_date

    return ""


def get_publication_year(publication_date_clean, publication_date_raw):
    """
    Extract publication year.
    """
    text = publication_date_clean or publication_date_raw
    match = re.search(r"\d{4}", text)

    if match:
        return int(match.group(0))

    return ""


def get_doi_from_rss(entry):
    """
    Try to extract DOI from common RSS fields or links.
    """
    possible_texts = []

    for key in ["id", "guid", "link", "title", "summary"]:
        if key in entry:
            possible_texts.append(str(entry[key]))

    combined_text = " ".join(possible_texts)

    doi_match = re.search(r"10\.\d{4,9}/[^\s\"<>]+", combined_text)

    if doi_match:
        return doi_match.group(0).rstrip(".")

    return ""


def extract_volume_issue_from_text(text):
    """
    Try to extract volume and issue from text.
    """
    volume = ""
    issue = ""

    if not text:
        return volume, issue

    volume_issue_patterns = [
        r"Volume\s+(\d+)\s*,?\s*Issue\s+(\d+)",
        r"Vol\.?\s+(\d+)\s*,?\s*No\.?\s+(\d+)",
        r"Vol\.?\s+(\d+)\s*,?\s*Issue\s+(\d+)",
        r"\b(\d+)\s*\(\s*(\d+)\s*\)"
    ]

    for pattern in volume_issue_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            volume = match.group(1)
            issue = match.group(2)
            return volume, issue

    volume_match = re.search(r"Volume\s+(\d+)|Vol\.?\s+(\d+)", text, flags=re.IGNORECASE)
    if volume_match:
        volume = volume_match.group(1) or volume_match.group(2)

    issue_match = re.search(r"Issue\s+(\d+)|No\.?\s+(\d+)", text, flags=re.IGNORECASE)
    if issue_match:
        issue = issue_match.group(1) or issue_match.group(2)

    return volume, issue


def get_volume_issue_from_rss(entry):
    """
    Extract volume and issue from RSS entry fields.
    """
    possible_texts = []

    for key in ["title", "summary", "id", "guid", "link"]:
        if key in entry:
            possible_texts.append(str(entry[key]))

    combined_text = " ".join(possible_texts)

    return extract_volume_issue_from_text(combined_text)


def query_crossref_by_doi(doi):
    """
    Look up one article in Crossref by DOI.
    """
    if not doi:
        return None

    url = f"{CROSSREF_API_BASE}/{quote(doi)}"

    try:
        response = requests.get(url, headers=CROSSREF_HEADERS, timeout=20)
        response.raise_for_status()
        data = response.json()
        return data.get("message", {})
    except Exception as error:
        print(f"  Crossref DOI lookup failed for {doi}: {error}")
        return None


def query_crossref_by_title(title, journal_name):
    """
    Search Crossref by title and journal name.
    We use only the top result because this is a metadata enrichment step.
    """
    if not title:
        return None

    params = {
        "query.bibliographic": f"{title} {journal_name}",
        "filter": "type:journal-article",
        "rows": 1
    }

    try:
        response = requests.get(
            CROSSREF_API_BASE,
            params=params,
            headers=CROSSREF_HEADERS,
            timeout=20
        )
        response.raise_for_status()
        data = response.json()
        items = data.get("message", {}).get("items", [])

        if items:
            return items[0]

        return None
    except Exception as error:
        print(f"  Crossref title search failed for {title}: {error}")
        return None


def get_crossref_abstract(item):
    """
    Extract and clean Crossref abstract when available.
    """
    if not item:
        return ""

    abstract = item.get("abstract", "")
    return clean_text(abstract)


def enrich_with_crossref(paper):
    """
    Improve RSS paper data using Crossref metadata.
    """
    crossref_item = None

    if paper.get("doi"):
        crossref_item = query_crossref_by_doi(paper["doi"])

    if not crossref_item:
        crossref_item = query_crossref_by_title(
            paper.get("title", ""),
            paper.get("journal_name", "")
        )

    if not crossref_item:
        paper["crossref_enriched"] = False
        return paper

    # DOI
    if not paper.get("doi") and crossref_item.get("DOI"):
        paper["doi"] = crossref_item["DOI"]

    # Volume and issue
    if not paper.get("volume") and crossref_item.get("volume"):
        paper["volume"] = str(crossref_item["volume"])

    if not paper.get("issue") and crossref_item.get("issue"):
        paper["issue"] = str(crossref_item["issue"])

    # Date
    crossref_date = choose_crossref_publication_date(crossref_item)
    if crossref_date:
        paper["publication_date_clean"] = crossref_date
        paper["publication_year"] = get_publication_year(crossref_date, "")

    # Authors
    crossref_authors = get_authors_from_crossref(crossref_item)
    if crossref_authors:
        paper["authors"] = crossref_authors

    # Abstract
    crossref_abstract = get_crossref_abstract(crossref_item)
    if crossref_abstract and len(crossref_abstract) > len(paper.get("abstract", "")):
        paper["abstract"] = crossref_abstract

    # URL
    if not paper.get("url") and crossref_item.get("URL"):
        paper["url"] = crossref_item["URL"]

    paper["crossref_enriched"] = True

    # Recalculate keyword matches after possible abstract update.
    paper["keyword_matches"] = find_keyword_matches(
        paper.get("title", ""),
        paper.get("abstract", "")
    )

    return paper


def collect_from_rss(feed_info):
    """
    Collect article data from one RSS feed.
    """
    feed = feedparser.parse(feed_info["feed_url"])
    papers = []
    today = date.today().isoformat()

    for entry in feed.entries:
        title = clean_text(entry.get("title", ""))
        raw_abstract = entry.get("summary", "")
        abstract = clean_abstract(raw_abstract, feed_info["journal_name"])
        publication_date_raw = get_publication_date_from_rss(entry)
        publication_date_clean = clean_publication_date(publication_date_raw)
        publication_year = get_publication_year(publication_date_clean, publication_date_raw)
        authors = get_authors_from_rss(entry)
        doi = get_doi_from_rss(entry)
        url = entry.get("link", "")
        volume, issue = get_volume_issue_from_rss(entry)

        paper = {
            "journal_name": feed_info["journal_name"],
            "title": title,
            "authors": authors,
            "publication_year": publication_year,
            "publication_date": publication_date_raw,
            "publication_date_clean": publication_date_clean,
            "volume": volume,
            "issue": issue,
            "abstract": abstract,
            "doi": doi,
            "url": url,
            "collection_date": today,
            "grade": feed_info["grade"],
            "keyword_matches": find_keyword_matches(title, abstract),
            "source_type": "rss",
            "crossref_enriched": False
        }

        papers.append(paper)

    return papers


def remove_duplicates(papers):
    """
    Remove duplicate papers.
    DOI is used first. If DOI is missing, URL is used.
    """
    unique_papers = []
    seen_keys = set()

    for paper in papers:
        key = paper["doi"] or paper["url"] or paper["title"]

        if key not in seen_keys:
            seen_keys.add(key)
            unique_papers.append(paper)

    return unique_papers


def save_papers(papers):
    """
    Save paper data to data/papers.json.
    """
    with open(PAPERS_FILE, mode="w", encoding="utf-8") as file:
        json.dump(papers, file, ensure_ascii=False, indent=2)


def main():
    load_journals()

    all_papers = []

    for feed_info in RSS_FEEDS:
        print(f"Collecting from {feed_info['journal_name']}...")
        papers = collect_from_rss(feed_info)
        print(f"  Collected {len(papers)} articles.")
        all_papers.extend(papers)

    all_papers = remove_duplicates(all_papers)

    enriched_papers = []

    for index, paper in enumerate(all_papers, start=1):
        print(f"Enriching {index}/{len(all_papers)}: {paper['title'][:80]}...")
        enriched_paper = enrich_with_crossref(paper)
        enriched_papers.append(enriched_paper)

        # Be polite to Crossref and avoid too many quick requests.
        time.sleep(0.5)

    enriched_papers.sort(
        key=lambda paper: str(paper.get("publication_date_clean", "")),
        reverse=True
    )

    save_papers(enriched_papers)

    print(f"Saved {len(enriched_papers)} articles to {PAPERS_FILE}.")


if __name__ == "__main__":
    main()
