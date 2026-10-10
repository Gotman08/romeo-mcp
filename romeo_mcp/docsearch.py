"""Recherche locale par sections, avec sources exactes et lecture reprenable.

L'index lexical reste en memoire : aucune base a transporter, aucun service
externe. Les empreintes stat invalident le cache quand le corpus change.
"""

# Copyright (c) 2026 Gotman08 (MIT)
from __future__ import annotations

import bisect
import hashlib
import math
import re
import threading
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


_STOP = set("a au aux avec ce ces cet cette dans de des du en et est etre il la le les leur ne on ou par pas pour que quel quelle quelles quels qui se ses son sur un une vos votre the and for of to in is how what les comment pourquoi peux peut faire utiliser".split())
MAX_PAGE_NAME = 1024


def normalized(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


def tokens(text: str) -> list[str]:
    words = re.findall(r"\w+", normalized(text))
    return [w[:-1] if len(w) > 4 and w.endswith("s") else w
            for w in words if w not in _STOP and (len(w) > 1 or w.isdigit())]


def resolve_page(directory: Path, page: str) -> Path:
    if not page or len(page) > MAX_PAGE_NAME:
        raise ValueError("Nom de page vide ou trop long (maximum 1024 caracteres). Consulte romeo://docs.")
    if "\x00" in page:
        raise ValueError("Nom de page invalide. Consulte romeo://docs.")
    root = directory.resolve()
    if not root.is_dir():
        raise ValueError(f"Documentation absente en {root}. Reinstaller le paquet avec son corpus ou verifier ROMEO_DOCS_DIR.")
    try:
        path = (root / page).resolve()
        is_page = path.suffix.lower() == ".md" and path.is_file()
    except (OSError, ValueError, RuntimeError):
        raise ValueError("Nom de page invalide. Consulte romeo://docs.") from None
    if not path.is_relative_to(root):
        raise ValueError("Chemin hors du dossier de documentation.")
    if not is_page:
        raise ValueError("Page Markdown introuvable. Consulte romeo://docs.")
    return path


@dataclass(frozen=True)
class Section:
    start: int  # indices de lignes, base zero, fin exclusive
    end: int
    headings: tuple[tuple[int, str], ...]
    terms: Counter


@dataclass(frozen=True)
class Page:
    name: str
    title: str
    source: str
    date: str
    sha256: str
    text: str
    lines: tuple[str, ...]
    offsets: tuple[int, ...]
    sections: tuple[Section, ...]


def load_page(path: Path, name: str) -> Page:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    lines = tuple(text.splitlines(keepends=True))
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    meta = {}
    body = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                body = i + 1
                break
            key, sep, value = lines[i].partition(":")
            if sep:
                meta[key] = value.strip().strip('"')
    title = meta.get("title", path.stem)
    boundaries = []
    trail: list[tuple[int, int, str]] = []
    fence = ""
    for i in range(body, len(lines)):
        line = lines[i]
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            mark = marker.group(1)
            if not fence:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence):
                fence = ""
            continue
        if fence:
            continue
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            level, label = len(heading.group(1)), heading.group(2)
            trail = [h for h in trail if h[0] < level]
            trail.append((level, i + 1, label))
            boundaries.append((i, tuple((n, label) for _, n, label in trail)))
    if not boundaries or boundaries[0][0] > body:
        boundaries.insert(0, (body, ()))
    sections = []
    for j, (start, headings) in enumerate(boundaries):
        end = boundaries[j + 1][0] if j + 1 < len(boundaries) else len(lines)
        content = "".join(lines[start:end])
        # Les metadonnees et la navigation sont disponibles a la lecture,
        # mais ne doivent pas concurrencer les explications du corpus.
        useful = re.sub(r"^\[Sommaire\].*$|^[←→].*$", "", content, flags=re.M)
        if not useful.strip() or (headings and headings[-1][1] == "Dans cette section"):
            continue
        terms = Counter(tokens(useful))
        terms.update(tokens(title) * 2)
        terms.update(tokens(" ".join(h for _, h in headings)) * 3)
        sections.append(Section(start, end, headings, terms))
    return Page(name, title, meta.get("source", ""), meta.get("scraped_at", ""),
                hashlib.sha256(raw).hexdigest(), text, lines, tuple(offsets), tuple(sections))


@dataclass(frozen=True)
class Corpus:
    signature: tuple
    revision: str
    pages: tuple[Page, ...]
    frequencies: Counter
    section_count: int
    average_length: float


_LOCK = threading.RLock()
_CACHE: dict[str, Corpus] = {}


def corpus(directory: Path) -> Corpus:
    root = directory.resolve()
    if not root.is_dir():
        raise ValueError(f"Documentation absente en {root}. Verifier ROMEO_DOCS_DIR ou reinstaller le paquet avec son corpus.")
    with _LOCK:
        # Relecture des stats seulement, sans reparcourir le texte a chaque appel.
        paths = sorted(p for p in root.rglob("*.md") if p.name not in ("README.md", "SOMMAIRE.md"))
        signature = tuple((p.relative_to(root).as_posix(), p.stat().st_mtime_ns,
                           p.stat().st_ctime_ns, p.stat().st_size) for p in paths)
        key = str(root)
        cached = _CACHE.get(key)
        if cached and signature == cached.signature:
            return cached
        pages = tuple(load_page(resolve_page(root, name), name) for name, *_ in signature)
        if not pages:
            raise ValueError(f"Le corpus {root} ne contient aucune page documentaire.")
        frequencies = Counter()
        lengths = []
        for page in pages:
            for section in page.sections:
                frequencies.update(section.terms.keys())
                lengths.append(section.terms.total())
        revision = hashlib.sha256("\n".join(p.name + ":" + p.sha256 for p in pages).encode()).hexdigest()
        result = Corpus(signature, revision, pages, frequencies, len(lengths), sum(lengths) / max(1, len(lengths)))
        # Borne le cache si plusieurs corpus sont testes depuis ce processus.
        if len(_CACHE) >= 4:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = result
        return result


def _metadata(page: Page) -> dict:
    return {"page": page.name, "title": page.title, "source_url": page.source,
            "scraped_at": page.date, "sha256": page.sha256}


def read_page(directory: Path, page: str, max_chars: int = 12000,
              start_line: int = 1, end_line: int | None = None,
              offset: int = 0, expected_sha256: str = "") -> dict:
    """offset est un curseur caractere relatif a la plage de lignes choisie."""
    path = resolve_page(directory, page)
    doc = load_page(path, path.relative_to(directory.resolve()).as_posix())
    if expected_sha256 and expected_sha256 != doc.sha256:
        raise ValueError("La page a change depuis l'extrait precedent. Relire depuis le debut pour conserver un contexte coherent.")
    last = len(doc.lines)
    end_line = last if end_line is None else int(end_line)
    if not (1 <= start_line <= max(last, 1)) or not (start_line <= end_line <= last or last == 0 and end_line == 0):
        raise ValueError(f"Plage de lignes invalide (page : {last} lignes).")
    begin = doc.offsets[start_line - 1] if last else 0
    finish = doc.offsets[end_line]
    if offset < 0 or offset > finish - begin:
        raise ValueError("offset hors de la plage demandee.")
    budget = max(500, min(int(max_chars), 60000))
    absolute = begin + offset
    content = doc.text[absolute:min(finish, absolute + budget)]
    next_offset = offset + len(content)
    truncated = begin + next_offset < finish
    line = min(last, bisect.bisect_right(doc.offsets, absolute)) if last else 0
    last_returned = min(last, bisect.bisect_right(doc.offsets, absolute + max(0, len(content) - 1))) if last else 0
    headings = next((s.headings for s in reversed(doc.sections) if s.start < max(line, 1)), ())
    next_args = {"page": doc.name, "start_line": start_line, "end_line": end_line,
                 "offset": next_offset, "max_chars": budget, "expected_sha256": doc.sha256} if truncated else None
    return {"ok": True, **_metadata(doc), "chars": len(doc.text), "total_lines": last,
            "start_line": line, "end_line": last_returned,
            "heading_path": [label for _, label in headings],
            "offset": offset, "returned_chars": len(content), "truncated": truncated,
            "content": content, "next_call": next_args}


def search(directory: Path, query: str, max_results: int = 20, context_lines: int = 2,
           max_chars: int = 18000, page_prefix: str = "", mode: str = "terms",
           offset: int = 0, expected_revision: str = "") -> dict:
    """BM25 sur les sections ; les extraits restent du texte source verbatim."""
    if not query.strip():
        raise ValueError("motif de recherche vide")
    if len(query) > 2000:
        raise ValueError("Requete trop longue (maximum 2000 caracteres).")
    if mode not in ("terms", "phrase"):
        raise ValueError("mode doit etre terms ou phrase.")
    if offset < 0:
        raise ValueError("offset doit etre positif ou nul.")
    terms = set(tokens(query))
    if not terms and mode == "terms":
        raise ValueError("La requete ne contient aucun terme significatif ; utiliser mode='phrase' pour un motif litteral.")
    data = corpus(directory)
    if expected_revision and expected_revision != data.revision:
        raise ValueError("Le corpus a change. Recommencer la recherche sans curseur pour conserver l'ordre des resultats.")
    limit = max(1, min(int(max_results), 60))
    budget = max(500, min(int(max_chars), 60000))
    radius = max(0, min(int(context_lines), 6))
    phrase = normalized(query.strip())
    candidates = []
    for page in data.pages:
        if page_prefix and not page.name.startswith(page_prefix.replace("\\", "/")):
            continue
        for section in page.sections:
            content = "".join(page.lines[section.start:section.end])
            found = terms & section.terms.keys()
            exact = phrase in normalized(content)
            if (mode == "phrase" and not exact) or (mode == "terms" and not found):
                continue
            length = section.terms.total()
            score = 0.0
            for term in found:
                count = section.terms[term]
                df = data.frequencies[term]
                idf = math.log(1 + (data.section_count - df + 0.5) / (df + 0.5))
                score += idf * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * length / max(1, data.average_length)))
            score *= len(found) / max(1, len(terms))
            if exact:
                score += 2
            candidates.append((score, page, section, found))
    candidates.sort(key=lambda row: (-row[0], row[1].name, row[2].start))
    matches = []
    used = 0
    for score, page, section, found in candidates[offset:offset + limit]:
        remaining = budget - used
        if remaining <= 0:
            break
        start, end = section.start, section.end
        hits = [n for n in range(start, end)
                if (phrase in normalized(page.lines[n]) if mode == "phrase" else terms & set(tokens(page.lines[n])))]
        hit = hits[0] if hits else start
        full = "".join(page.lines[start:end])
        allowance = min(remaining, 6000)
        if len(full) > allowance:
            # Fenetre autour de la correspondance ; read_doc rend toujours la
            # section complete avec continuation, meme pour un tres long bloc.
            start, end = max(start, hit - radius), min(end, hit + radius + 1)
        begin, finish = page.offsets[start], page.offsets[end]
        if finish - begin > allowance:
            # Une seule ligne de tableau peut depasser le budget. Centrer le
            # fragment sur le terme pour ne pas rendre un extrait sans match.
            hit_column = next((m.start() for m in re.finditer(r"\w+", page.lines[hit])
                               if terms & set(tokens(m.group()))), 0)
            char_hit = page.offsets[hit] + hit_column
            begin = max(begin, char_hit - min(allowance // 3, radius * 80))
            finish = min(finish, begin + allowance)
        excerpt = page.text[begin:finish]
        visible_start = bisect.bisect_right(page.offsets, begin)
        visible_end = bisect.bisect_right(page.offsets, max(begin, finish - 1))
        partial = begin != page.offsets[section.start] or finish != page.offsets[section.end]
        headings = [{"line": n, "title": label} for n, label in section.headings]
        matches.append({**_metadata(page), "line": hit + 1, "start_line": visible_start,
                        "end_line": visible_end, "section_start_line": section.start + 1,
                        "section_end_line": section.end, "headings": headings,
                        "start_column": begin - page.offsets[visible_start - 1] + 1,
                        "score": round(score, 4), "matched_terms": sorted(found),
                        "excerpt": excerpt, "excerpt_truncated": partial,
                        "read_args": {"page": page.name, "start_line": section.start + 1,
                                      "end_line": section.end, "expected_sha256": page.sha256}})
        used += len(excerpt)
    next_offset = offset + len(matches)
    more = next_offset < len(candidates)
    next_args = {"query": query, "max_results": limit, "context_lines": radius,
                 "max_chars": budget, "page_prefix": page_prefix, "mode": mode,
                 "offset": next_offset, "expected_revision": data.revision} if more else None
    return {"ok": True, "query": query, "mode": mode, "count": len(matches),
            "total_matches": len(candidates), "truncated": more, "matches": matches,
            "excerpt_chars": used, "corpus_pages": len(data.pages), "revision": data.revision,
            "next_call": next_args,
            "note": "Extraits verbatim, classement lexical. Lire la section via read_doc(**read_args), puis next_call pour toute suite. Les titres parents donnent le contexte ; lire leurs lignes pour les prerequis. Les valeurs du corpus sont datees : verifier l'etat courant du cluster."}
