"""Serveur MCP ROMEO : assemblage et point d'entree.

Les outils vivent dans des modules thematiques ; les importer ici suffit a les
enregistrer, car c'est le decorateur `outil` qui les declare aupres du serveur.
Ce fichier reste volontairement mince : il dit de quoi le serveur est fait.

Les noms sont reexportes pour que `romeo_mcp.server.<outil>` continue de
designer chaque outil -- c'est ainsi que les suites de tests les atteignent.
"""

from __future__ import annotations
import time
_IMPORT_STARTED = time.monotonic()

from .noyau import *  # noqa: F401,F403 - reexport volontaire
from .noyau import server
from .outils_calcul import *  # noqa: F401,F403
from .outils_contexte import *  # noqa: F401,F403
from .outils_donnees import *  # noqa: F401,F403
from .outils_execution import *  # noqa: F401,F403
from .outils_mesure import *  # noqa: F401,F403
from .outils_accompagnement import *  # noqa: F401,F403
from .outils_diagnostics import *  # noqa: F401,F403
from .outils_transferts import *  # noqa: F401,F403
from .outils_checkpoints import *  # noqa: F401,F403
from .observability import TIMINGS
TIMINGS.record("server_initialization", time.monotonic() - _IMPORT_STARTED)

def main() -> None:
    """Point d'entree : transport stdio."""
    server.run("stdio")

if __name__ == "__main__":
    main()
