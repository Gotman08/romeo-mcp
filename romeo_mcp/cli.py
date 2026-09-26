"""Installation locale et demarrage stdio sans sortie parasite sur le protocole."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys

from . import __version__
from .config import config_path, save, setting


def main() -> None:
    from . import updates
    try:
        updates.dispatch()
    except (ValueError, OSError) as exc:
        raise SystemExit(f"Mise a jour : {exc}") from exc
    if len(sys.argv) == 1:
        updates.start_notice()
        from .server import main as serve
        serve()
        return
    parser = argparse.ArgumentParser(description="MCP ROMEO : configurer son acces ou demarrer le serveur stdio.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="action", required=True)
    configure = sub.add_parser("configure", help="enregistrer le projet et l'alias SSH hors du depot")
    configure.add_argument("--account", help="code de VOTRE projet dans le portail ROMEO")
    configure.add_argument("--host", help="alias SSH configure sur ce poste")
    configure.add_argument("--qos")
    configure.add_argument("--profile", choices=("essential", "full"), help="profil d'outils conserve hors du depot")
    serve_parser = sub.add_parser("serve", help="demarrer le serveur stdio")
    serve_parser.add_argument("--profile", choices=("essential", "full"))
    doctor = sub.add_parser("doctor", help="verifications locales ou distantes en lecture seule")
    doctor.add_argument("--live", action="store_true", help="verifier SSH, projet Slurm, partitions et quotas")
    doctor.add_argument("--timeout", type=int, default=20, help="delai par lecture distante, entre 2 et 60 secondes")
    doctor.add_argument("--project-group", default="", help="groupe GPFS si different du projet Slurm")
    export = sub.add_parser("export-job", help="exporter une fiche de reproductibilite hors du depot")
    export.add_argument("job_id")
    export.add_argument("--output-dir", default="")
    export.add_argument("--code-dir", default="")
    export.add_argument("--data-file", action="append", default=[])
    export.add_argument("--offline", action="store_true")
    update = sub.add_parser("update", help="verifier, installer ou annuler une mise a jour GitHub")
    operation = update.add_mutually_exclusive_group()
    operation.add_argument("--check", action="store_true", help="consulter la derniere release sans installer")
    operation.add_argument("--rollback", action="store_true", help="reactiver l'environnement precedent")
    update.add_argument("--yes", action="store_true", help="confirmation explicite sans dialogue interactif")
    update.add_argument("--json", action="store_true", help="reponse structuree pour --check uniquement")
    args = parser.parse_args()
    try:
        if args.action == "update":
            if args.json and not args.check:
                parser.error("--json s'utilise avec update --check")
            updates.command(check_only=args.check, revert=args.rollback, yes=args.yes, json_output=args.json)
        elif args.action == "configure":
            values = {key: value for key, value in (
                ("ROMEO_ACCOUNT", args.account), ("ROMEO_HOST", args.host),
                ("ROMEO_QOS", args.qos), ("ROMEO_TOOL_PROFILE", args.profile)) if value is not None}
            if not values:
                parser.error("configure attend --account, --host, --qos ou --profile")
            path = save(values)
            print(f"Configuration enregistree hors du depot : {path}")
            print("Elle sera chargee par les prochains processus MCP. Aucune cle SSH n'est copiee.")
        elif args.action == "serve":
            if args.profile:
                os.environ["ROMEO_TOOL_PROFILE"] = args.profile
            updates.start_notice()
            from .server import main as serve
            serve()
        elif args.action == "export-job":
            from .reproducibility import export_report
            from .ssh import session
            try:
                print(json.dumps(export_report(args.job_id, output_dir=args.output_dir,
                    code_dir=args.code_dir, data_files=args.data_file, live=not args.offline), indent=2))
            finally:
                if not args.offline:
                    session().close()
        else:
            from .cluster import require_account
            from .noyau import _docs_dir
            from .docsearch import corpus
            docs = corpus(_docs_dir())
            account = setting("ROMEO_ACCOUNT").strip()
            from .profiles import validate_profile
            result = {"version": __version__, "python": sys.version.split()[0],
                              "mcp": importlib.metadata.version("mcp"),
                              "account_configured": bool(account),
                              "documentation_pages": len(docs.pages),
                              "config_file_present": config_path().is_file(),
                              "ssh_checked": False, "live": args.live,
                              "tool_profile": validate_profile(setting("ROMEO_TOOL_PROFILE", "full"))}
            if not account:
                print(json.dumps(result, indent=2))
                parser.exit(1, "Projet absent : python -m romeo_mcp configure --account VOTRE_PROJET\n")
            require_account(account)
            if args.live:
                from .doctor import live_checks
                result.update(live_checks(timeout=args.timeout, project_group=args.project_group))
            print(json.dumps(result, indent=2))
            if args.live and not result["ok"]:
                parser.exit(1, "Diagnostic incomplet : suivre les messages de chaque verification.\n")
    except (ValueError, OSError, importlib.metadata.PackageNotFoundError) as exc:
        parser.exit(1, f"{exc}\n")
