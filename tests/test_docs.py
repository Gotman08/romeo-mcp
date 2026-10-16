"""Contrats documentaires : portabilite, recherche et restitution sans perte."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from romeo_mcp import docsearch, noyau, outils_contexte
from tools import verify_corpus
from tools.install_mcp import dossier_docs

try:
    import requests
    from tools import romeo_doc_scraper
except ImportError:  # extra facultatif `.[docs]` : requests, beautifulsoup4, markdownify
    requests = romeo_doc_scraper = None

ROOT = Path(__file__).resolve().parents[1]
STORAGE = "ressources/romeo_2025/espaces_de_stockage.md"


class DocumentationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="romeo docs ")
        self.root = Path(self.tmp.name)
        self.text = '''---
title: "Stockage personnel et projet"
source: "https://romeo.univ-reims.fr/documentation/exemple/"
scraped_at: "2026-09-26"
---
# Stockage

## Quotas du projet

Les quotas du projet limitent le stockage collectif.
Attention : après expiration du délai de grâce, les écritures sont bloquées.

```bash
# Cette ligne de code ne doit pas devenir un titre
mmlsquota --block-size auto -g test-project gpfs
```

## Utilisation personnelle

Le scratch contient les données des calculs en cours.
'''
        (self.root / "stockage.md").write_text(self.text, encoding="utf-8", newline="\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ranked_question_keeps_warning_and_code(self):
        query = "Pourquoi les ecritures du PROJET sont bloquees apres le delai de grace ?"
        self.assertNotIn(query.lower(), self.text.lower())
        result = docsearch.search(self.root, query)
        match = result["matches"][0]
        self.assertEqual(match["headings"][-1]["title"], "Quotas du projet")
        self.assertIn("Attention", match["excerpt"])
        self.assertIn("```bash", match["excerpt"])
        self.assertIn("mmlsquota", match["excerpt"])
        self.assertFalse(match["excerpt_truncated"])
        self.assertEqual(match["source_url"], "https://romeo.univ-reims.fr/documentation/exemple/")
        read = docsearch.read_page(self.root, **match["read_args"])
        self.assertEqual(read["content"], match["excerpt"])

    def test_phrase_prefix_and_exact_count(self):
        result = docsearch.search(self.root, "mmlsquota --block-size", mode="phrase", max_results=1)
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["truncated"])
        self.assertEqual(docsearch.search(self.root, "quota", page_prefix="absent/")["count"], 0)
        self.assertEqual(docsearch.search(self.root, "xxintrouvablexx")["count"], 0)

    def test_search_pagination_budget_and_stale_cursor(self):
        first = docsearch.search(self.root, "stockage", max_results=1, max_chars=500)
        self.assertTrue(first["truncated"])
        self.assertLessEqual(first["excerpt_chars"], 500)
        all_matches = list(first["matches"])
        next_args = first["next_call"]
        while next_args:
            result = docsearch.search(self.root, **next_args)
            all_matches.extend(result["matches"])
            next_args = result["next_call"]
        self.assertEqual(len(all_matches), first["total_matches"])
        identities = {(m["page"], m["section_start_line"]) for m in all_matches}
        self.assertEqual(len(identities), len(all_matches))
        (self.root / "stockage.md").write_text(self.text + "\nUn changement\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "corpus a change"):
            docsearch.search(self.root, **first["next_call"])

    def test_lossless_read_including_long_line_and_range(self):
        long_text = self.text + "\n" + "é" * 2500 + "\nFIN\n"
        (self.root / "stockage.md").write_text(long_text, encoding="utf-8", newline="\n")
        args = {"page": "stockage.md", "max_chars": 500}
        parts = []
        while args:
            result = docsearch.read_page(self.root, **args)
            self.assertLessEqual(len(result["content"]), 500)
            parts.append(result["content"])
            args = result["next_call"]
        self.assertEqual("".join(parts), long_text)
        subset = docsearch.read_page(self.root, "stockage.md", start_line=9, end_line=16)
        self.assertEqual(subset["content"], "".join(long_text.splitlines(keepends=True)[8:16]))
        with self.assertRaisesRegex(ValueError, "page a change"):
            docsearch.read_page(self.root, "stockage.md", expected_sha256="obsolete")

    def test_cache_refresh_and_safe_paths(self):
        first = docsearch.corpus(self.root)
        self.assertIs(first, docsearch.corpus(self.root))
        (self.root / "stockage.md").write_text(self.text + "\ntermenouveauunique\n", encoding="utf-8")
        result = docsearch.search(self.root, "termenouveauunique")
        self.assertEqual(result["count"], 1)
        self.assertNotEqual(first.revision, result["revision"])
        with self.assertRaisesRegex(ValueError, "hors du dossier"):
            docsearch.read_page(self.root, "../secret.md")
        (self.root / "secret.txt").write_text("pas une page", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Markdown introuvable"):
            docsearch.read_page(self.root, "secret.txt")
        for kwargs in ({"start_line": 0}, {"end_line": 9999}, {"offset": -1}):
            with self.assertRaises(ValueError):
                docsearch.read_page(self.root, "stockage.md", **kwargs)

    def test_unknown_page_errors_do_not_reflect_large_or_invalid_inputs(self):
        for page in ('x' * 1024, 'x' * 1025, 'x' * 65536 + '.md', '😀' * 1048576,
                     'x\x00.md', 'missing\npage.md', ''):
            with self.subTest(size=len(page)), patch.dict(os.environ, {'ROMEO_DOCS_DIR': str(self.root)}):
                result = outils_contexte.read_doc(page, max_chars=500)
                self.assertFalse(result['ok'])
                self.assertLess(len(result['error']), 250)
                self.assertLess(len(json.dumps(result)), 1000)
                self.assertLess(len(outils_contexte.docs_page(page)), 250)

    def test_match_near_end_of_very_long_line(self):
        text = "# Catalogue\n\n" + "A " * 1800 + "ciblerarefin\n"
        (self.root / "catalogue.md").write_text(text, encoding="utf-8")
        match = docsearch.search(self.root, "ciblerarefin", max_chars=500)["matches"][0]
        self.assertIn("ciblerarefin", match["excerpt"])
        self.assertTrue(match["excerpt_truncated"])
        self.assertEqual(match["start_line"], 3)
        self.assertGreater(match["start_column"], 1)

    def test_configuration_and_error_messages(self):
        with patch.dict(os.environ, {"ROMEO_DOCS_DIR": str(self.root)}):
            self.assertEqual(noyau._docs_dir(), self.root)
            self.assertTrue(outils_contexte.search_docs("quota")["ok"])
        with patch.dict(os.environ, {"ROMEO_DOCS_DIR": "relative-corpus"}):
            self.assertEqual(noyau._docs_dir(), ROOT / "relative-corpus")
        with patch.dict(os.environ, {"ROMEO_DOCS_DIR": str(self.root / "absent")}):
            self.assertFalse(outils_contexte.search_docs("quota")["ok"])
        with patch.dict(os.environ, {"ROMEO_DOCS_DIR": ""}):
            self.assertEqual(dossier_docs(ROOT), ROOT / "romeo_mcp" / "documentation")
            self.assertEqual(noyau._docs_dir(), dossier_docs(ROOT))

    def test_real_corpus_queries(self):
        with patch.dict(os.environ, {"ROMEO_DOCS_DIR": ""}):
            cases = [
                ("quota home scratch projet", "espaces_de_stockage.md"),
                ("delai grace quota ecriture", "espaces_de_stockage.md"),
                ("charger logiciels spack armgpu", "charger_ses_logiciels.md"),
                ("srun MPI multi noeuds", "utiliser_openmpi.md"),
            ]
            for query, expected in cases:
                with self.subTest(query=query):
                    result = outils_contexte.search_docs(query, max_results=5, page_prefix="ressources/romeo_2025/")
                    self.assertTrue(result["ok"], result)
                    self.assertTrue(any(m["page"].endswith(expected) for m in result["matches"]), result)

    def test_relocated_package_from_unrelated_cwd(self):
        relocated = self.root / "mcp deplace"
        shutil.copytree(ROOT / "romeo_mcp", relocated / "romeo_mcp", ignore=shutil.ignore_patterns("__pycache__"))
        env = dict(os.environ, PYTHONPATH=str(relocated), ROMEO_DOCS_DIR="", PYTHONUTF8="1")
        code = ("from pathlib import Path; from romeo_mcp import noyau, outils_contexte; "
                "assert noyau._docs_dir() == Path(noyau.__file__).with_name('documentation').resolve(); "
                "assert 'mcp deplace' in str(noyau._docs_dir()); "
                "r=outils_contexte.search_docs('quota projet'); assert r['ok'] and r['count'], r")
        result = subprocess.run([sys.executable, "-c", code], cwd=self.root, env=env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_offline_mcp_protocol(self):
        from mcp import ClientSession, StdioServerParameters, stdio_client

        async def run():
            env = dict(os.environ, ROMEO_DOCS_DIR="", PYTHONPATH=str(ROOT),
                       ROMEO_MCP_DB=str(self.root / "jobs.db"))
            params = StdioServerParameters(command=sys.executable, args=["-m", "romeo_mcp"], env=env, cwd=str(self.root))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    schemas = {t.name: t.input_schema for t in (await session.list_tools()).tools}
                    self.assertIn("page_prefix", schemas["search_docs"]["properties"])
                    self.assertIn("offset", schemas["read_doc"]["properties"])
                    result = await session.call_tool("search_docs", {"query": "quota home scratch projet", "max_results": 3})
                    payload = json.loads(result.content[0].text)
                    self.assertTrue(payload["ok"], payload)
                    match = next(m for m in payload["matches"] if m["page"] == STORAGE)
                    result = await session.call_tool("read_doc", match["read_args"])
                    self.assertTrue(json.loads(result.content[0].text)["ok"])
                    result = await session.read_resource("romeo://docs/" + STORAGE)
                    self.assertIn("mmlsquota", result.contents[0].text)
                    result = await session.read_resource("romeo://docs")
                    self.assertIn("sommaire", result.contents[0].text.lower())
                    result = await session.read_resource("romeo://docs/ressources/romeo_2025/Logiciels/Architecture%20Aarch64.md")
                    self.assertIn("# Architecture Aarch64", result.contents[0].text)
                    for size in (65536, 1048576):
                        result = await session.call_tool('read_doc', {'page': 'x' * size + '.md', 'max_chars': 500})
                        self.assertFalse(result.structured_content['ok'])
                        self.assertLess(len(result.model_dump_json()), 1000)
                    healthy = await session.call_tool('read_doc', {'page': STORAGE, 'max_chars': 500})
                    self.assertTrue(healthy.structured_content['ok'])

        asyncio.run(run())


SITE = "https://romeo.univ-reims.fr/documentation"

#: Page d'authentification en miniature : les hrefs `[...]` sont ceux que le site
#: sert aujourd'hui (crochets laisses dans la source Markdown amont), avec en
#: plus une ancre et la forme relative sans `/documentation/`.
AUTH_HTML = """<!doctype html><html lang="fr"><head><title>Authentification | ROMEO</title></head><body>
<nav class="navbar"><a href="/documentation/">Documentation</a></nav>
<main><article>
<h1>Authentification au portail ROMEO</h1>
<p>Voir la <a href="/documentation/[https://romeo.univ-reims.fr/documentation/2.5.charte]">charte d'utilisation</a>
(<a href="/documentation/[https://romeo.univ-reims.fr/documentation/2.5.charte#article-1]">article 1</a>),
le <a href="/documentation/[https://romeo-ticket.univ-reims.fr/]">support ROMEO</a>
ou <a href="[https://romeo-ticket.univ-reims.fr/]">le guichet</a>.</p>
<ul>
<li>Support : <a href="/documentation/[https://romeo-ticket.univ-reims.fr/]">https://romeo-ticket.univ-reims.fr/</a></li>
<li>Technique : <a href="/documentation/[contact@example.org]">contact@example.org</a></li>
<li>Securite : <a href="/documentation/[securite@example.org]">securite@example.org</a></li>
</ul>
<p>Liens ordinaires : <a href="/documentation/2.5.charte">la charte</a>,
<a href="https://www.renater.fr/">RENATER</a>, <a href="mailto:contact@example.org">ecrire</a>,
<a href="/documentation/files/exemple.py">un exemple</a>.</p>
</article></main></body></html>"""

CHARTE_HTML = """<!doctype html><html lang="fr"><head><title>Charte | ROMEO</title></head><body>
<main><article>
<h1>Charte d'utilisation</h1>
<h2 class="anchor" id="article-1">Article 1<a class="hash-link" href="#article-1" title="Lien direct vers Article 1">&#8203;</a></h2>
<p>Texte de l'article.</p>
</article></main></body></html>"""

INDEX_HTML = """<!doctype html><html lang="fr"><head><title>Documentation | ROMEO</title></head><body>
<main><article>
<h1>Documentation ROMEO</h1>
<p><a href="/documentation/authentification">Authentification</a></p>
</article></main></body></html>"""

EXPECTED_NORMALIZATION = {
    "/documentation/[https://romeo.univ-reims.fr/documentation/2.5.charte]": "2.5.charte.md",
    "/documentation/[https://romeo.univ-reims.fr/documentation/2.5.charte#article-1]": "2.5.charte.md#article-1",
    "/documentation/[https://romeo-ticket.univ-reims.fr/]": "https://romeo-ticket.univ-reims.fr/",
    "[https://romeo-ticket.univ-reims.fr/]": "https://romeo-ticket.univ-reims.fr/",
    "/documentation/[contact@example.org]": "mailto:contact@example.org",
    "/documentation/[securite@example.org]": "mailto:securite@example.org",
}


class FakeResponse:
    def __init__(self, status: int, text: str, content_type: str = "text/html; charset=utf-8"):
        self.status_code = status
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"content-type": content_type}
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("{} Client Error".format(self.status_code))


class FakeSession:
    """Sert quelques pages et rend 404 pour tout le reste, en gardant la trace des appels."""

    def __init__(self, routes: dict[str, str]):
        self.routes = routes
        self.requested: list[str] = []
        self.headers = {}

    def get(self, url, timeout=None):
        self.requested.append(url)
        if url in self.routes:
            return FakeResponse(200, self.routes[url])
        return FakeResponse(404, "")


@unittest.skipIf(romeo_doc_scraper is None,
                 "dependances facultatives absentes : python -m pip install -e '.[docs]'")
class DocScraperLinkTests(unittest.TestCase):
    """Collecte hors ligne : les cibles laissees entre crochets en amont."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="romeo scraper ")
        self.out = Path(self.tmp.name)
        self.scraper = romeo_doc_scraper.RomeoDocScraper(str(self.out))

    def tearDown(self):
        self.tmp.cleanup()

    def collect_auth_page(self) -> str:
        page = self.scraper.parse_page(SITE + "/authentification", AUTH_HTML)
        return self.scraper.save_page(page).read_text(encoding="utf-8")

    def test_bracketed_hrefs_resolve_to_real_targets(self):
        markdown = self.collect_auth_page()
        for expected in (
            "[charte d'utilisation](2.5.charte.md)",
            "[article 1](2.5.charte.md#article-1)",
            "[support ROMEO](https://romeo-ticket.univ-reims.fr/)",
            "[le guichet](https://romeo-ticket.univ-reims.fr/)",
            "[https://romeo-ticket.univ-reims.fr/](https://romeo-ticket.univ-reims.fr/)",
            "[contact@example.org](mailto:contact@example.org)",
            "[securite@example.org](mailto:securite@example.org)",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, markdown)
        self.assertNotRegex(markdown, r"\]\([^)]*[\[\]]")
        self.assertNotIn(".md]", markdown)
        self.assertEqual(self.scraper.stats.errors, 0)

    def test_ordinary_links_keep_their_behaviour(self):
        markdown = self.collect_auth_page()
        for expected in (
            "[la charte](2.5.charte.md)",
            "[RENATER](https://www.renater.fr/)",
            "[ecrire](mailto:contact@example.org)",
            "[un exemple](https://romeo.univ-reims.fr/documentation/files/exemple.py)",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, markdown)

    def test_fake_targets_are_never_queued(self):
        page = self.scraper.parse_page(SITE + "/authentification", AUTH_HTML)
        self.assertEqual(page.links, {SITE + "/", SITE + "/2.5.charte"})

    def test_normalization_is_recorded_per_page(self):
        self.collect_auth_page()
        self.assertEqual(self.scraper.link_normalization, {"authentification.md": EXPECTED_NORMALIZATION})

    def test_local_target_follows_page_depth(self):
        page = self.out / "ressources" / "guide.md"
        text = self.scraper.clean_markdown(
            "[charte](/documentation/[https://romeo.univ-reims.fr/documentation/2.5.charte#article-1])", page)
        self.assertEqual(text, "[charte](../2.5.charte.md#article-1)")
        self.assertEqual(
            self.scraper.link_normalization["ressources/guide.md"],
            {"/documentation/[https://romeo.univ-reims.fr/documentation/2.5.charte#article-1]": "2.5.charte.md#article-1"},
        )

    def test_bracket_shapes(self):
        resolve = self.scraper.resolve_bracketed_href
        cases = {
            "/documentation/[https://romeo.univ-reims.fr/documentation/2.5.charte]":
                ("documentation", "/documentation/2.5.charte"),
            "[https://romeo.univ-reims.fr/documentation/ressources/connexion_ssh#cles]":
                ("documentation", "/documentation/ressources/connexion_ssh#cles"),
            "/documentation/[https://romeo.univ-reims.fr/documentation/ressources/connexion_ssh]#cles":
                ("documentation", "/documentation/ressources/connexion_ssh#cles"),
            "/documentation/[https://romeo.univ-reims.fr/documentation/]":
                ("documentation", "/documentation/"),
            "./[https://romeo-ticket.univ-reims.fr/]": ("external", "https://romeo-ticket.univ-reims.fr/"),
            "/documentation/[https://romeo.univ-reims.fr/portail]": ("external", "https://romeo.univ-reims.fr/portail"),
            "https://romeo.univ-reims.fr/documentation/[contact@example.org]": ("mailto", "mailto:contact@example.org"),
            "/documentation/[mailto:contact@example.org]": ("mailto", "mailto:contact@example.org"),
            "/documentation/[n'importe quoi]": ("unresolved", None),
            "/documentation/2.5.charte": None,
            "https://example.org/a[1]": None,
            "http://[::1]/documentation": None,
            "#section": None,
        }
        for href, expected in cases.items():
            with self.subTest(href=href):
                self.assertEqual(resolve(href), expected)

    def test_unreadable_brackets_are_counted_once_and_kept_visible(self):
        page = self.out / "page.md"
        with contextlib.redirect_stdout(io.StringIO()):
            text = self.scraper.clean_markdown(
                "[a](/documentation/[n'importe quoi]) puis [b](/documentation/[n'importe quoi])", page)
        absolute = SITE + "/[n'importe quoi]"
        self.assertEqual(text, "[a]({0}) puis [b]({0})".format(absolute))
        self.assertEqual(self.scraper.stats.errors, 1)
        self.assertEqual(self.scraper.link_normalization, {})

    def test_full_run_never_requests_fake_targets_and_passes_verification(self):
        session = FakeSession({
            SITE + "/sitemap.xml": "<urlset>{}</urlset>".format("".join(
                "<url><loc>{}</loc></url>".format(SITE + name)
                for name in ("/", "/authentification", "/2.5.charte"))),
            SITE + "/": INDEX_HTML,
            SITE + "/authentification": AUTH_HTML,
            SITE + "/2.5.charte": CHARTE_HTML,
        })
        self.scraper.session = session
        with patch.object(romeo_doc_scraper, "REQUEST_DELAY", 0), contextlib.redirect_stdout(io.StringIO()):
            self.scraper.scrape()

        self.assertEqual([url for url in session.requested if "[" in url or "]" in url], [])
        self.assertEqual(self.scraper.stats.errors, 0)
        manifest = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["errors"], 0)
        self.assertEqual(manifest["pages"], 3)
        self.assertEqual(manifest["link_normalization"], {"authentification.md": EXPECTED_NORMALIZATION})

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = verify_corpus.main(self.out)
        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("CORPUS CONFORME", buffer.getvalue())


class CorpusVerificationTests(unittest.TestCase):
    """`verify_corpus` : casse exacte des fichiers et ancres `#fragment`."""

    PAGE_A = (
        "---\ntitle: A\n---\n# A\n\n## Mise en route\n\n## Mise en route\n\n"
        "```bash\n# pas un titre\n```\n\n"
        "Voir [la suite](dossier/b.md#présentation) et [le second](#mise-en-route-1).\n"
    )
    PAGE_B = (
        "# B\n\n## Présentation[\u200b](#présentation \"Lien direct vers Présentation\")\n\n"
        "Retour [a](../a.md#mise-en-route).\n"
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="romeo corpus ")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def verify(self, **overrides):
        files = {
            "SOMMAIRE.md": "# Sommaire\n\n- [A](a.md)\n- [B](dossier/b.md)\n",
            "a.md": self.PAGE_A,
            "dossier/b.md": self.PAGE_B,
        }
        files.update(overrides)
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        manifest = {"errors": 0, "files": {
            name: hashlib.sha256((self.root / name).read_bytes()).hexdigest() for name in files}}
        (self.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = verify_corpus.main(self.root)
        return code, buffer.getvalue()

    def test_valid_anchors_pass_and_are_counted(self):
        code, output = self.verify()
        self.assertEqual(code, 0, output)
        self.assertIn("ancres resolvables       : 3 (introuvables : 0)", output)
        self.assertIn("CORPUS CONFORME", output)

    def test_percent_encoded_anchor_is_accepted(self):
        code, output = self.verify(**{"a.md": self.PAGE_A.replace("#présentation", "#pr%C3%A9sentation")})
        self.assertEqual(code, 0, output)

    def test_missing_anchors_are_reported(self):
        for label, old, new, expected in (
            ("autre page", "dossier/b.md#présentation", "dossier/b.md#introuvable",
             "ancre introuvable dans a.md -> dossier/b.md#introuvable"),
            ("meme page", "(#mise-en-route-1)", "(#mise-en-route-2)",
             "ancre introuvable dans a.md -> #mise-en-route-2"),
            ("titre dans un bloc de code", "(#mise-en-route-1)", "(#pas-un-titre)",
             "ancre introuvable dans a.md -> #pas-un-titre"),
            ("majuscule", "dossier/b.md#présentation", "dossier/b.md#Présentation",
             "ancre introuvable dans a.md -> dossier/b.md#Présentation"),
        ):
            with self.subTest(label):
                code, output = self.verify(**{"a.md": self.PAGE_A.replace(old, new)})
                self.assertEqual(code, 1, output)
                self.assertIn(expected, output)

    def test_wrong_case_is_a_dead_link(self):
        code, output = self.verify(**{"a.md": self.PAGE_A.replace("dossier/b.md#", "Dossier/b.md#")})
        self.assertEqual(code, 1, output)
        self.assertIn("lien mort dans a.md -> Dossier/b.md", output)

    def test_exact_case_helper_is_independent_of_the_filesystem(self):
        self.verify()
        listings = {}
        self.assertTrue(verify_corpus.casse_exacte(self.root, self.root / "dossier" / "b.md", listings))
        self.assertTrue(verify_corpus.casse_exacte(self.root, self.root / "dossier" / ".." / "a.md", listings))
        self.assertFalse(verify_corpus.casse_exacte(self.root, self.root / "Dossier" / "b.md", listings))
        self.assertFalse(verify_corpus.casse_exacte(self.root, self.root / "dossier" / "B.md", listings))
        self.assertTrue(verify_corpus.casse_exacte(self.root, self.root.parent / "hors-corpus", listings))

    def test_heading_ids(self):
        ancre = verify_corpus.ancre
        self.assertEqual(ancre("Article 1\u00a0: Présentation de ROMEO"), "article-1-présentation-de-romeo")
        self.assertEqual(ancre("Architecture x86\\_64"), "architecture-x86_64")
        self.assertEqual(ancre("5.4 Raisonnement (`reasoning_effort`)"), "54-raisonnement-reasoning_effort")
        self.assertEqual(ancre("Voir [le guide](x.md) et **gras**"), "voir-le-guide-et-gras")
        self.assertEqual(
            verify_corpus.ancres_de("# Un\n\n## Un\n\n## Un\n"), {"un", "un-1", "un-2"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
