import csv
import json
from datetime import date
from pathlib import Path


# Project folders
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

JOURNALS_FILE = DATA_DIR / "journals.csv"
PAPERS_FILE = DATA_DIR / "papers.json"


def load_journals():
    """
    Read the journal list from data/journals.csv.
    Return only journals included in the first implementation.
    """
    journals = []

    with open(JOURNALS_FILE, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            if row["first_implementation"].lower() == "yes":
                journals.append(row)

    return journals


def create_sample_papers(journals):
    """
    Create sample paper data using the first three journals.
    This is temporary. Later, this function will be replaced by real RSS/Crossref collection.
    """
    today = date.today().isoformat()

    sample_templates = [
        {
            "title": "How publics make sense of scientific uncertainty in climate communication",
            "abstract": "This sample article examines how publics interpret scientific uncertainty in climate communication and how trust in expertise shapes policy support.",
            "keyword_matches": ["scientific uncertainty", "climate change", "trust", "policy support"]
        },
        {
            "title": "Valuation, expertise, and the politics of biodiversity metrics",
            "abstract": "This sample article explores how biodiversity valuation metrics are constructed through expert knowledge, institutional practices, and political negotiation.",
            "keyword_matches": ["valuation", "biodiversity", "expertise", "politicization"]
        },
        {
            "title": "Carbon markets and public responsibility in energy transitions",
            "abstract": "This sample article investigates how carbon markets reshape public responsibility and sustainability narratives in energy transition debates.",
            "keyword_matches": ["carbon market", "sustainability", "responsibility"]
        }
    ]

    papers = []

    for index, template in enumerate(sample_templates):
        journal = journals[index]

        paper = {
            "journal_name": journal["journal_name"],
            "title": template["title"],
            "authors": ["Sample Author A", "Sample Author B"],
            "publication_year": 2026,
            "publication_date": "2026-07-01",
            "abstract": template["abstract"],
            "doi": f"10.0000/sample-{index + 1}",
            "url": "https://example.com",
            "collection_date": today,
            "grade": journal["grade"],
            "keyword_matches": template["keyword_matches"],
            "source_type": "sample"
        }

        papers.append(paper)

    return papers


def save_papers(papers):
    """
    Save paper data to data/papers.json.
    """
    with open(PAPERS_FILE, mode="w", encoding="utf-8") as file:
        json.dump(papers, file, ensure_ascii=False, indent=2)


def main():
    journals = load_journals()
    papers = create_sample_papers(journals)
    save_papers(papers)

    print(f"Loaded {len(journals)} first-implementation journals.")
    print(f"Saved {len(papers)} sample papers to {PAPERS_FILE}.")


if __name__ == "__main__":
    main()
