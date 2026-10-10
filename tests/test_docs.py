"""Contrats documentaires : portabilite, recherche et restitution sans perte."""

from __future__ import annotations

import asyncio
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
from tools.install_mcp import dossier_docs

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
