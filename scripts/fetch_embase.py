#!/usr/bin/env python3
"""Fetch Embase/Scopus results for systematic literature review."""

import urllib.parse
import json
import os
import sys
import urllib.request

API_KEY = os.environ["EMBASE_API_KEY"]
BASE_URL = "https://api.elsevier.com/content/search/scopus"
FIELDS = "dc:identifier,dc:title,dc:creator,prism:publicationName,prism:coverDate,prism:doi,dc:description,citedby-count,prism:issn,subtype,authkeywords"

queries = [
    'TITLE-ABS-KEY("cancer patient*" AND "long term care" AND (knowledge OR attitude OR behavior) AND (nurse* OR physician* OR "health professional*"))',
    'TITLE-ABS-KEY(neoplasm* AND "long-term care" AND referral AND (barrier* OR facilitator* OR willingness))',
    'TITLE-ABS-KEY(oncolog* AND "continuing care" AND (perception* OR awareness OR "care coordination"))',
    'TITLE-ABS-KEY("elderly" AND "cancer" AND "long-term care" AND ("care needs" OR "supportive care" OR "palliative"))',
    'TITLE-ABS-KEY(("tumor care" OR "tumour care" OR "cancer care") AND "long-term care" AND (knowledge OR attitude)) AND SUBJAREA(MEDI OR NURS OR HEAL)',
]

query_labels = ["q1", "q2", "q3", "q4", "q5_fallback"]


def fetch_query(query):
    encoded = urllib.parse.quote(query)
    url = f"{BASE_URL}?query={encoded}&count=25&field={FIELDS}"
    req = urllib.request.Request(url, headers={
        "X-ELS-APIKey": API_KEY,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    all_articles = []
    total_per_query = []

    for i, q in enumerate(queries):
        label = query_labels[i]
        print(f"Fetching {label}...", file=sys.stderr)
        data = fetch_query(q)
        sr = data["search-results"]
        total = int(sr["opensearch:totalResults"])
        total_per_query.append(total)
        print(f"  {label}: {total} results", file=sys.stderr)

        if total == 0:
            continue

        entries = sr.get("entry", [])
        for e in entries:
            # Skip error entries
            if e.get("error"):
                continue

            title = e.get("dc:title", "")
            authors = e.get("dc:creator", "")
            journal = e.get("prism:publicationName", "")
            cover_date = e.get("prism:coverDate", "")
            year = cover_date[:4] if cover_date else ""
            doi = e.get("prism:doi", "")
            issn = e.get("prism:issn", "")
            cited_by = int(e.get("citedby-count", 0))
            abstract = e.get("dc:description", "")
            keywords = e.get("authkeywords", "")

            all_articles.append({
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": year,
                "doi": doi,
                "issn": issn,
                "cited_by": cited_by,
                "abstract": abstract or "",
                "keywords": keywords or "",
                "source_db": "embase",
                "query_matched": label,
            })

    output = {
        "source": "embase",
        "query_date": "2026-03-31",
        "queries": queries,
        "total_results_per_query": total_per_query,
        "articles": all_articles,
    }

    outpath = "/Users/htlin/cancer-ltc-kab-study/output-cancer-ltc-kab/embase_raw.json"
    with open(outpath, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(all_articles)} articles to {outpath}", file=sys.stderr)
    print(f"Total per query: {list(zip(query_labels, total_per_query))}", file=sys.stderr)


if __name__ == "__main__":
    main()
