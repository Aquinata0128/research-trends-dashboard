import csv
import json
import re
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser


# Project folders
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

JOURNALS_FILE = DATA_DIR / "journals.csv"
PAPERS_FILE = DATA_DIR / "papers.json"


# First real RSS collection targets.
# We start with SAGE journals because their RSS structure is relatively stable.
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
    Clean simple HTML tags and extra spaces from RSS text.
    """
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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


def get_authors(entry):
    """
    Extract authors from an RSS entry.
    RSS feeds do not always use the same author format.
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

    return authors


def get_publication_date(entry):
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
    This makes sorting and filtering easier in the dashboard.
    """
    if not publication_date:
        return ""

    try:
        parsed_date = parsedate_to_datetime(publication_date)
        return parsed_date.date().isoformat()
    except Exception:
        pass

    # If the date is already close to YYYY-MM-DD, keep the first match.
    match = re.search(r"\d{4}-\d{2}-\d{2}", publication_date)
    if match:
        return match.group(0)

    # Last fallback: keep only the year if available.
    year_match = re.search(r"\d{4}", publication_date)
    if year_match:
        return year_match.group(0)

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


def get_doi(entry):
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
    RSS feeds are inconsistent, so this is a best-effort function.

    Examples it tries to catch:
    - Volume 34, Issue 2
    - Vol. 34, Issue 2
    - 34(2)
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


def get_volume_issue(entry):
    """
    Extract volume and issue from RSS entry fields.
    """
    possible_texts = []

    for key in ["title", "summary", "id", "guid", "link"]:
        if key in entry:
            possible_texts.append(str(entry[key]))

    combined_text = " ".join(possible_texts)

    return extract_volume_issue_from_text(combined_text)


def collect_from_rss(feed_info):
    """
    Collect article data from one RSS feed.
    """
    feed = feedparser.parse(feed_info["feed_url"])
    papers = []
    today = date.today().isoformat()

    for entry in feed.entries:
        title = clean_text(entry.get("title", ""))
        abstract = clean_text(entry.get("summary", ""))
        publication_date_raw = get_publication_date(entry)
        publication_date_clean = clean_publication_date(publication_date_raw)
        publication_year = get_publication_year(publication_date_clean, publication_date_raw)
        authors = get_authors(entry)
        doi = get_doi(entry)
        url = entry.get("link", "")
        volume, issue = get_volume_issue(entry)

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
            "source_type": "rss"
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

    # Sort newest first when possible.
    all_papers.sort(
        key=lambda paper: str(paper.get("publication_date_clean", "")),
        reverse=True
    )

    save_papers(all_papers)

    print(f"Saved {len(all_papers)} articles to {PAPERS_FILE}.")


if __name__ == "__main__":
    main()
