"""Check that cited sources exist: resolve DOIs through Crossref and compare titles.

A resolved DOI shows the citation is real; it does not show that the claim
matches the paper. The agent still reads the abstract or paper for each claim.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

import requests

from .common import now


DOI = re.compile(r"10\.\d{4,9}/[^\s)\]>,;]+", re.I)


STOP = set("about after again also because before being between both could during each from have into made make more most "
           "only other same such than that their them then there these they this those through under were what when which "
           "while with would your".split())


def lookup(citation: str, journal: str = "", says: str = "") -> dict | None:
    """Best Europe PMC match for a loose citation such as 'Kubo et al. 2001' (a lead to verify, not proof)."""
    match = re.match(r"([A-Za-z'\-]+).*?((?:19|20)\d{2})", citation)
    if not match:
        return None
    author, year = match.groups()
    keywords = [w for w in re.findall(r"[a-z]{5,}", says.lower()) if w not in STOP][:6]
    topic = f" AND ({' OR '.join(keywords)})" if keywords else ""
    queries = [f'AUTH:"{author}" AND PUB_YEAR:{year} AND JOURNAL:"{journal}"{topic}',
               f'AUTH:"{author}" AND PUB_YEAR:{year}{topic}', f'AUTH:"{author}" AND PUB_YEAR:{year} AND JOURNAL:"{journal}"']
    def norm(text):
        return re.sub(r"\(.*?\)|[^a-z ]", "", (text or "").lower()).strip()

    for query in queries:
        try:
            response = requests.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search", timeout=30,
                                    params={"query": query, "format": "json", "pageSize": 5, "resultType": "lite"})
            results = response.json().get("resultList", {}).get("result", []) if response.ok else []
        except (requests.RequestException, ValueError):
            return None
        if results:
            # Prefer the cited journal (e.g. "J Appl Physiol" matches "J Appl Physiol (1985)").
            item = next((r for r in results if journal and norm(r.get("journalTitle")) == norm(journal)), results[0])
            return {"doi": item.get("doi"), "pmid": item.get("pmid"), "title": item.get("title"),
                    "journal": item.get("journalTitle"), "year": item.get("pubYear"), "authors": item.get("authorString")}
    return None


def verify(project) -> list[dict]:
    results = []
    for source in project.sources.get("sources", []):
        found = DOI.search(f"{source.get('locator', '')} {source.get('title', '')}")
        result = {"id": source["id"], "status": "unchecked", "detail": "no DOI in title/locator; check the locator manually"}
        if found:
            doi = found.group(0).rstrip(".")
            try:
                response = requests.get(f"https://api.crossref.org/works/{doi}", timeout=30,
                                        headers={"User-Agent": "fitness-workflow-kit/0.3 (source check)"})
            except requests.RequestException as exc:
                result.update(status="unreachable", detail=type(exc).__name__)
            else:
                if response.status_code == 404:
                    result.update(status="missing", detail=f"DOI {doi} does not resolve")
                elif response.ok:
                    message = response.json().get("message", {})
                    title = (message.get("title") or [""])[0]
                    year = ((message.get("issued") or {}).get("date-parts") or [[None]])[0][0]
                    journal = (message.get("container-title") or [""])[0]
                    ours = re.sub(r"[^a-z0-9]+", " ", source.get("title", "").lower())
                    theirs = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
                    score = 1.0 if theirs and theirs in ours else SequenceMatcher(None, theirs, ours).ratio()
                    result.update(status="ok" if score >= 0.8 else "mismatch", doi=doi, title=title, year=year,
                                  journal=journal, score=round(score, 2),
                                  detail=f"{title} ({journal}, {year})")
                else:
                    result.update(status="unreachable", detail=f"HTTP {response.status_code}")
        results.append(result)
    project.state["source_check"] = {"at": now(), "results": results}
    project.save()
    return results
