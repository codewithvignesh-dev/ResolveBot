"""Policy retrieval: split policies.md, join manifest.json, filter by status/date, BM25 search."""
import json
import math
import re
from collections import Counter
from datetime import date

from business_rules import fmt_date

_STOP = set("a an the is are was were be to of in on for and or do does did i my me we you your it its this that "
            "what how can will with at by from as about if when which there any have has get".split())
_SECTION = re.compile(r"^#{2,4}\s+(§[\d.]+)\s*(.*)$")
_DOC_ID = re.compile(r"\*\*Document ID:\*\*\s*([\w\-]+)")
_cache: dict = {}


def _tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9₹]+", text.lower()):
        if w in _STOP:
            continue
        for suf in ("ing", "ed", "es", "s"):
            if len(w) > len(suf) + 2 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


def _parse(policies_path: str, manifest_path: str) -> list[dict]:
    """Return one chunk per numbered section, each tagged with its manifest metadata."""
    with open(manifest_path, encoding="utf-8") as f:
        manifest = {m["doc_id"]: m for m in json.load(f)}
    with open(policies_path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    docs, cur = [], None
    for line in lines:
        if line.startswith("# "):
            cur = {"title": line[2:].strip(), "doc_id": None, "chunks": []}
            docs.append(cur)
        elif cur is not None:
            m = _DOC_ID.search(line)
            if m and cur["doc_id"] is None:
                cur["doc_id"] = m.group(1)
                continue
            sm = _SECTION.match(line)
            if sm:
                cur["chunks"].append({"section": sm.group(1), "heading": sm.group(2).strip(), "body": []})
            elif cur["chunks"]:
                cur["chunks"][-1]["body"].append(line)
    chunks = []
    for d in docs:
        meta = manifest.get(d["doc_id"])
        if not meta:
            continue
        for c in d["chunks"]:
            body = "\n".join(c["body"]).strip()
            if body:
                chunks.append({
                    "doc_id": d["doc_id"], "section": c["section"], "heading": c["heading"], "text": body,
                    "doc_title": meta["title"], "doc_type": meta["doc_type"], "status": meta["status"],
                    "effective_date": meta["effective_date"],
                })
    return chunks


def _chunks(policies_path: str, manifest_path: str) -> list[dict]:
    key = (policies_path, manifest_path)
    if key not in _cache:
        _cache[key] = _parse(policies_path, manifest_path)
    return _cache[key]


def search(policies_path: str, manifest_path: str, query: str, today: date, k: int = 5) -> list[dict]:
    pool = []
    for c in _chunks(policies_path, manifest_path):
        if c["status"] != "current":
            continue  # superseded documents are never used
        eff = date.fromisoformat(c["effective_date"])
        pool.append((c, eff))
    if not pool or not _tokens(query):
        return []
    docs = [_tokens(f"{c['heading']} {c['heading']} {c['doc_title']} {c['text']}") for c, _ in pool]
    n, avgdl = len(docs), sum(len(d) for d in docs) / len(docs)
    df = Counter(t for d in docs for t in set(d))
    q = set(_tokens(query))
    scored = []
    for (c, eff), d in zip(pool, docs):
        tf, s, head = Counter(d), 0.0, set(_tokens(c["heading"]))
        for t in q:
            if tf[t]:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * tf[t] * 2.5 / (tf[t] + 1.5 * (0.25 + 0.75 * len(d) / avgdl))
                if t in head:
                    s += idf * 1.5  # a query word in the section heading is a strong signal
        if c["doc_type"] == "faq":
            s *= 0.9  # policy outranks FAQ when they overlap
        if s > 0:
            scored.append((s, c, eff))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return []
    best = scored[0][0]
    results = []
    for s, c, eff in scored[:k]:
        if s < 0.4 * best:
            continue
        in_effect = eff <= today
        results.append({
            "doc_id": c["doc_id"], "section": c["section"], "title": c["heading"],
            "doc_type": c["doc_type"], "text": c["text"],
            "applies": "in effect" if in_effect
            else f"NOT YET IN EFFECT - future change starting {fmt_date(eff)}",
        })
    return results
