    existing_papers = load_existing_papers()

    print(f"Loaded {len(existing_papers)} existing papers from {PAPERS_FILE}.")

    combined_papers = existing_papers + enriched_papers
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
