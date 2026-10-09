"""Compare tous les exemples, parametres et liens source aux contrats MCP sans SSH."""
from __future__ import annotations

import ast
import asyncio
import json
import os
from pathlib import Path
import re
import sys

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def source_locations() -> dict[str, tuple[str, int]]:
    locations = {}
    for path in (ROOT / "romeo_mcp").glob("outils_*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "outil"
                       for d in node.decorator_list):
                    locations[node.name] = (path.name, node.lineno)
    return locations


async def check() -> dict:
    # Uniquement tools/list et les fichiers de documentation ; aucun outil appele.
    from romeo_mcp.server import server
    from romeo_mcp.issue_public import PUBLIC_TOOLS
    original_profile = server.tool_profile
    try:
        server.tool_profile = "expert"
        tools = await server.list_tools()
    finally:
        server.tool_profile = original_profile
    locations = source_locations()
    errors, empty = [], []
    for tool in tools:
        path = ROOT / "docs" / "tools" / (tool.name + ".md")
        if not path.is_file():
            errors.append(f"{tool.name}: fiche absente")
            continue
        text = path.read_text(encoding="utf-8")
        examples = re.findall(r"```json\s*\n(.*?)\n```", text, re.S)
        if not examples:
            errors.append(f"{tool.name}: exemple JSON absent")
        schema = tool.input_schema
        for raw in examples:
            try:
                example = json.loads(raw)
                for error in Draft202012Validator(schema).iter_errors(example):
                    errors.append(f"{tool.name}: exemple incompatible ({error.message})")
                if example == {}:
                    empty.append(tool.name)
                    if not any(term in text.lower() for term in ("aucun argument", "aucun paramètre", "paramètres facultatifs", "paramètres sont facultatifs")):
                        errors.append(f"{tool.name}: objet vide non explique")
            except ValueError:
                errors.append(f"{tool.name}: JSON invalide")
        # Les sous-champs d'un objet ont leur propre tableau et ne sont pas
        # des arguments de premier niveau du contrat MCP.
        parameter_table = re.search(r"^\| (?:Paramètre|Nom) \|[^\n]*\n(?:^\|[^\n]*\n)*", text, re.M)
        table = parameter_table.group() if parameter_table else ""
        documented = set(re.findall(r"^\| `([^`]+)` \|", table, re.M))
        expected = set(schema.get("properties", {}))
        if documented != expected:
            errors.append(f"{tool.name}: parametres documentes differents du schema")
        if table:
            def cells(line):
                return [cell.strip() for cell in re.split(r"(?<!\\)\|", line)[1:-1]]

            rows = table.splitlines()
            header = cells(rows[0])
            for line in rows[2:]:
                values = cells(line)
                if len(values) != len(header):
                    errors.append(f"{tool.name}: nombre de colonnes incorrect dans le tableau")
                    continue
                name = values[0].strip("`")
                prop = schema.get("properties", {}).get(name)
                if prop is None:
                    continue
                if "Obligatoire" in header:
                    required = name in schema.get("required", [])
                    if (values[header.index("Obligatoire")].lower() == "oui") != required:
                        errors.append(f"{tool.name}.{name}: caractere obligatoire incorrect")
                default_column = next((i for i, title in enumerate(header) if title in ("Défaut", "Defaut")), None)
                if default_column is not None and "default" in prop:
                    raw = values[default_column].strip("`")
                    try:
                        value = json.loads(raw)
                    except ValueError:
                        value = {"None": None, "True": True, "False": False, "Vide": "", "Chaîne vide": ""}.get(raw, raw)
                    if value != prop["default"]:
                        errors.append(f"{tool.name}.{name}: defaut different du schema")
        if tool.name in locations:
            filename, line = locations[tool.name]
            if f"../../romeo_mcp/{filename}#L{line}" not in text:
                errors.append(f"{tool.name}: lien source incorrect")
    expected_public = {tool.name for tool in tools if not tool.name.startswith("mcp_issue_")} | {"server", "terminal"}
    if PUBLIC_TOOLS != expected_public:
        errors.append("Catalogue des outils publiables incoherent avec tools/list")
    return {"ok": not errors, "tools_checked": len(tools), "empty_examples": empty, "errors": errors}


def main() -> int:
    os.environ["ROMEO_TOOL_PROFILE"] = "expert"
    result = asyncio.run(check())
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
