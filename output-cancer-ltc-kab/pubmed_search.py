#!/usr/bin/env python3
"""PubMed search script for cancer-LTC-KAB systematic review."""

import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date

# Load .env file manually
def load_dotenv(path=".env"):
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

load_dotenv("/Users/htlin/cancer-ltc-kab-study/.env")
API_KEY = os.environ.get("PUBMED_API_KEY", "")
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

QUERIES = [
    '(cancer[tiab] OR neoplasm[tiab] OR oncology[tiab]) AND ("long-term care"[tiab] OR "long term care"[tiab]) AND (knowledge[tiab] OR attitude*[tiab] OR perception*[tiab])',
    '"Neoplasms"[MeSH] AND "Long-Term Care"[MeSH] AND ("Health Knowledge, Attitudes, Practice"[MeSH] OR "Attitude of Health Personnel"[MeSH])',
    '"Neoplasms"[MeSH] AND "Long-Term Care"[MeSH] AND ("Referral and Consultation"[MeSH] OR referral[tiab] OR "discharge planning"[tiab])',
    '(elderly[tiab] OR "older adult*"[tiab] OR aged[tiab]) AND (cancer[tiab] OR neoplasm*[tiab]) AND "long-term care"[tiab] AND (barrier*[tiab] OR willingness[tiab] OR facilitator*[tiab])',
    '("Oncology Nursing"[MeSH] OR "oncology nurs*"[tiab]) AND ("Long-Term Care"[MeSH] OR "long-term care"[tiab]) AND (perception*[tiab] OR knowledge[tiab])',
]


def esearch(query: str, retmax: int = 25) -> tuple[list[str], int]:
    """Search PubMed and return (pmids, total_count)."""
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "retmode": "json",
        "retmax": retmax,
        "term": query,
        "api_key": API_KEY,
    })
    url = f"{BASE}/esearch.fcgi?{params}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read())
    result = data.get("esearchresult", {})
    pmids = result.get("idlist", [])
    count = int(result.get("count", 0))
    return pmids, count


def efetch(pmids: list[str]) -> str:
    """Fetch full PubMed XML for given PMIDs."""
    if not pmids:
        return ""
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "retmode": "xml",
        "id": ",".join(pmids),
        "api_key": API_KEY,
    })
    url = f"{BASE}/efetch.fcgi?{params}"
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read().decode("utf-8")


def parse_articles(xml_str: str) -> dict[str, dict]:
    """Parse PubMed XML into article dicts keyed by PMID."""
    if not xml_str:
        return {}
    root = ET.fromstring(xml_str)
    articles = {}
    for art in root.findall(".//PubmedArticle"):
        rec = {}
        # PMID
        pmid_el = art.find(".//PMID")
        pmid = pmid_el.text if pmid_el is not None else ""
        rec["pmid"] = pmid

        # Title
        title_el = art.find(".//ArticleTitle")
        rec["title"] = "".join(title_el.itertext()) if title_el is not None else ""

        # Abstract
        abs_parts = []
        for abs_el in art.findall(".//AbstractText"):
            label = abs_el.get("Label", "")
            text = "".join(abs_el.itertext())
            if label:
                abs_parts.append(f"{label}: {text}")
            else:
                abs_parts.append(text)
        rec["abstract"] = " ".join(abs_parts)

        # Authors
        authors = []
        for author in art.findall(".//Author"):
            ln = author.find("LastName")
            fn = author.find("ForeName")
            if ln is not None and fn is not None:
                authors.append(f"{ln.text}, {fn.text}")
            elif ln is not None:
                authors.append(ln.text)
            else:
                cn = author.find("CollectiveName")
                if cn is not None:
                    authors.append(cn.text)
        rec["authors"] = "; ".join(authors)

        # Journal
        journal_el = art.find(".//Journal/Title")
        rec["journal"] = journal_el.text if journal_el is not None else ""

        # Year
        year_el = art.find(".//PubDate/Year")
        if year_el is None:
            medline_el = art.find(".//PubDate/MedlineDate")
            rec["year"] = (medline_el.text[:4] if medline_el is not None else "")
        else:
            rec["year"] = year_el.text

        # DOI
        doi = ""
        for aid in art.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text or ""
                break
        if not doi:
            for eid in art.findall(".//ELocationID"):
                if eid.get("EIdType") == "doi":
                    doi = eid.text or ""
                    break
        rec["doi"] = doi

        # ISSN
        issn_el = art.find(".//ISSN")
        rec["issn"] = issn_el.text if issn_el is not None else ""

        # MeSH terms
        mesh = []
        for mh in art.findall(".//MeshHeading"):
            desc = mh.find("DescriptorName")
            if desc is not None:
                mesh.append(desc.text)
        rec["mesh_terms"] = "; ".join(mesh)

        # Keywords
        kws = []
        for kw in art.findall(".//Keyword"):
            if kw.text:
                kws.append(kw.text)
        rec["keywords"] = "; ".join(kws)

        rec["source_db"] = "pubmed"
        articles[pmid] = rec
    return articles


def main():
    all_pmids = {}  # pmid -> query label
    total_per_query = []

    # Step 1: search each query
    for i, q in enumerate(QUERIES, 1):
        label = f"q{i}"
        print(f"Searching {label}: {q[:80]}...")
        pmids, count = esearch(q)
        total_per_query.append(count)
        new = 0
        for p in pmids:
            if p not in all_pmids:
                all_pmids[p] = label
                new += 1
        print(f"  Found {count} total, retrieved {len(pmids)}, {new} new unique")
        time.sleep(0.35)  # rate limit

    unique_pmids = list(all_pmids.keys())
    print(f"\nTotal unique PMIDs: {len(unique_pmids)}")

    # Step 2: fetch in batches of 200
    all_articles = {}
    for i in range(0, len(unique_pmids), 200):
        batch = unique_pmids[i:i+200]
        print(f"Fetching records {i+1}-{i+len(batch)}...")
        xml = efetch(batch)
        parsed = parse_articles(xml)
        all_articles.update(parsed)
        time.sleep(0.35)

    # Step 3: build output
    articles_list = []
    for pmid, query_label in all_pmids.items():
        art = all_articles.get(pmid, {})
        if not art:
            art = {"pmid": pmid, "title": "", "authors": "", "journal": "",
                   "year": "", "doi": "", "issn": "", "abstract": "",
                   "keywords": "", "mesh_terms": "", "source_db": "pubmed"}
        art["query_matched"] = query_label
        articles_list.append(art)

    output = {
        "source": "pubmed",
        "query_date": str(date.today()),
        "queries": QUERIES,
        "total_results_per_query": total_per_query,
        "articles": articles_list,
    }

    out_path = "/Users/htlin/cancer-ltc-kab-study/output-cancer-ltc-kab/pubmed_raw.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(articles_list)} articles to {out_path}")
    print(f"Results per query: {total_per_query}")


if __name__ == "__main__":
    main()
