import csv
import json
import re
import time
from datetime import date, datetime, timedelta
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
ARCHIVE_DIR = DATA_DIR / "archive"

# Keep papers from the recent 24 months in data/papers.json.
RETENTION_DAYS = 730


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
    },
    {
        "journal_name": "Environmental Communication",
        "grade": "A",
        "feed_url": "https://www.tandfonline.com/action/showFeed?type=etoc&feed=rss&jc=renc20"
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

CROSSREF_HEADERS = {
    "User-Agent": "ResearchTrendsDashboard/0.1"
}


def load_journals():
    """
    Read the journal list from data/journals.csv.
    This is kept for later expansion.
    """
    journals = []

    if not JOURNALS_FILE.exists():
        return journals

    with open(JOURNALS_FILE, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            journals.append(row)

    return journals


def load_existing_papers():
    """
    Load existing papers from data/papers.json.
    Existing papers should not be enriched again.
    """
    if not PAPERS_FILE.exists():
        return []

    try:
        with open(PAPERS_FILE, mode="r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as error:
        print(f"Could not load existing papers: {error}")
        return []


def clean_text(text):
    """
    Clean simple HTML tags, HTML entities, and extra spaces.
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


def get_paper_key(paper):
    """
    Create a stable key for duplicate detection.
    DOI is best. URL is second. Title is fallback.
    """
    doi = clean_text(paper.get("doi", "")).lower()
    url = clean_text(paper.get("url", "")).lower()
    title = clean_text(paper.get("title", "")).lower()

    if doi:
        return f"doi:{doi}"

    if url:
        return f"url:{url}"

    return f"title:{title}"


def build_existing_paper_map(existing_papers):
    """
    Create a dictionary of existing papers.
    This allows us to skip Crossref calls for already-known papers.
    """
    existing_map = {}

    for paper in existing_papers:
        key = get_paper_key(paper)

        if key:
            existing_map[key] = paper

    return existing_map


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
    Improve one new RSS paper using Crossref metadata.
    Existing papers should not come here again.
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

    if not paper.get("doi") and crossref_item.get("DOI"):
        paper["doi"] = crossref_item["DOI"]

    if not paper.get("volume") and crossref_item.get("volume"):
        paper["volume"] = str(crossref_item["volume"])

    if not paper.get("issue") and crossref_item.get("issue"):
        paper["issue"] = str(crossref_item["issue"])

    crossref_date = choose_crossref_publication_date(crossref_item)
    if crossref_date:
        paper["publication_date_clean"] = crossref_date
        paper["publication_year"] = get_publication_year(crossref_date, "")

    crossref_authors = get_authors_from_crossref(crossref_item)
    if crossref_authors:
        paper["authors"] = crossref_authors

    crossref_abstract = get_crossref_abstract(crossref_item)
    if crossref_abstract and len(crossref_abstract) > len(paper.get("abstract", "")):
        paper["abstract"] = crossref_abstract

    if not paper.get("url") and crossref_item.get("URL"):
        paper["url"] = crossref_item["URL"]

    paper["crossref_enriched"] = True

    paper["keyword_matches"] = find_keyword_matches(
        paper.get("title", ""),
        paper.get("abstract", "")
    )

    return paper


def collect_from_rss(feed_info):
    """
    Collect raw article data from one RSS feed.
    This does not call Crossref.
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
    DOI is used first. If DOI is missing, URL is used. Title is fallback.
    """
    unique_papers = []
    seen_keys = set()

    for paper in papers:
        key = get_paper_key(paper)

        if key not in seen_keys:
            seen_keys.add(key)
            unique_papers.append(paper)

    return unique_papers


def parse_clean_date(date_text):
    """
    Convert publication_date_clean text to a Python date object.
    """
    if not date_text:
        return None

    try:
        if len(date_text) >= 10:
            return datetime.strptime(date_text[:10], "%Y-%m-%d").date()

        if len(date_text) == 4 and date_text.isdigit():
            return date(int(date_text), 1, 1)

        return None
    except Exception:
        return None


def split_recent_and_archive(papers):
    """
    Split papers into recent papers and archive papers.
    """
    today = date.today()
    cutoff_date = today - timedelta(days=RETENTION_DAYS)

    recent_papers = []
    archive_papers = []

    for paper in papers:
        paper_date = parse_clean_date(paper.get("publication_date_clean", ""))

        # Keep unknown-date papers in the main file for now.
        if paper_date is None:
            recent_papers.append(paper)
            continue

        if paper_date >= cutoff_date:
            recent_papers.append(paper)
        else:
            archive_papers.append(paper)

    return recent_papers, archive_papers


def group_archive_by_year(papers):
    """
    Group archived papers by publication year.
    """
    grouped = {}

    for paper in papers:
        year = paper.get("publication_year")

        if not year:
            paper_date = parse_clean_date(paper.get("publication_date_clean", ""))
            year = paper_date.year if paper_date else "unknown"

        year = str(year)

        if year not in grouped:
            grouped[year] = []

        grouped[year].append(paper)

    return grouped


def save_papers(papers):
    """
    Save recent papers to data/papers.json.
    """
    with open(PAPERS_FILE, mode="w", encoding="utf-8") as file:
        json.dump(papers, file, ensure_ascii=False, indent=2)


def save_archive_papers(archive_papers):
    """
    Save old papers to data/archive/papers_YYYY.json.
    Existing archive files are merged with newly archived papers.
    """
    if not archive_papers:
        return

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    grouped_archive = group_archive_by_year(archive_papers)

    for year, papers_for_year in grouped_archive.items():
        archive_file = ARCHIVE_DIR / f"papers_{year}.json"
        existing_archive = []

        if archive_file.exists():
            try:
                with open(archive_file, mode="r", encoding="utf-8") as file:
                    existing_archive = json.load(file)
            except Exception as error:
                print(f"Could not load archive file {archive_file}: {error}")

        merged_archive = remove_duplicates(existing_archive + papers_for_year)

        merged_archive.sort(
            key=lambda paper: str(paper.get("publication_date_clean", "")),
            reverse=True
        )

        with open(archive_file, mode="w", encoding="utf-8") as file:
            json.dump(merged_archive, file, ensure_ascii=False, indent=2)

        print(f"Saved {len(merged_archive)} archived papers to {archive_file}.")


def main():
    load_journals()

    existing_papers = load_existing_papers()
    existing_paper_map = build_existing_paper_map(existing_papers)

    print(f"Loaded {len(existing_papers)} existing papers.")
    print(f"Existing paper keys: {len(existing_paper_map)}")

    new_or_updated_papers = []
    skipped_existing_count = 0
    new_paper_count = 0

    for feed_info in RSS_FEEDS:
        print(f"Collecting from {feed_info['journal_name']}...")
        rss_papers = collect_from_rss(feed_info)
        print(f"  RSS entries found: {len(rss_papers)}")

        for paper in rss_papers:
            paper_key = get_paper_key(paper)

            if paper_key in existing_paper_map:
                skipped_existing_count += 1
                continue

            new_paper_count += 1
            print(f"  New paper found: {paper['title'][:80]}")

            enriched_paper = enrich_with_crossref(paper)
            new_or_updated_papers.append(enriched_paper)

            # Only sleep after actual Crossref work.
            time.sleep(0.5)

    print(f"Skipped existing RSS papers: {skipped_existing_count}")
    print(f"New papers enriched with Crossref: {new_paper_count}")

    combined_papers = existing_papers + new_or_updated_papers
    combined_papers = remove_duplicates(combined_papers)

    combined_papers.sort(
        key=lambda paper: str(paper.get("publication_date_clean", "")),
        reverse=True
    )

    recent_papers, archive_papers = split_recent_and_archive(combined_papers)

    recent_papers.sort(
        key=lambda paper: str(paper.get("publication_date_clean", "")),
        reverse=True
    )

    save_papers(recent_papers)
    save_archive_papers(archive_papers)

    print(f"Saved {len(recent_papers)} recent papers to {PAPERS_FILE}.")
    print(f"Moved or kept {len(archive_papers)} older papers in archive.")


if __name__ == "__main__":
    main()
