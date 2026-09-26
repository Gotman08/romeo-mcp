"""Verification manuelle du transport SSH persistant (necessite ROMEO joignable)."""

import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from romeo_mcp.ssh import RomeoSession, SSHTimeout, clamp  # noqa: E402


def main() -> int:
    s = RomeoSession()

    t0 = time.monotonic()
    r = s.run("hostname; uname -m")
    print("1) premiere commande rc={} en {:.0f} ms -> {}".format(
        r.rc, (time.monotonic() - t0) * 1000, r.stdout.replace("\n", " | ")))

    t1 = time.monotonic()
    r = s.run("echo reutilisation")
    print("2) seconde commande en {:.0f} ms (doit etre << 600 ms) -> {}".format(
        (time.monotonic() - t1) * 1000, r.stdout))

    r = s.run("exit 42")
    print("3) code de retour propage :", r.rc, "attendu 42", "OK" if r.rc == 42 else "ECHEC")

    r = s.run("echo sur_stderr >&2")
    print("4) stderr fusionne :", repr(r.stdout), "OK" if "sur_stderr" in r.stdout else "ECHEC")

    r = s.run("module avail 2>&1 | head -3")
    has_modules = "modulefiles" in r.stdout or "cuda" in r.stdout
    print("5) `module` disponible (shell de login) :", "OK" if has_modules else "ECHEC")
    print("   ", r.stdout.replace("\n", " | ")[:120])

    print("6) user={} home={} scratch={}".format(s.user, s.home, s.scratch))

    r = s.run("pwd", cwd="/tmp")
    print("7) cwd honore :", r.stdout, "OK" if r.stdout.strip() == "/tmp" else "ECHEC")

    r = s.run("pwd")
    print("8) pas de fuite d'etat :", r.stdout,
          "OK" if r.stdout.strip() != "/tmp" else "ECHEC")

    r = s.run("seq 1 5000", max_chars=300)
    print("9) troncature :", "OK" if r.truncated and len(r.stdout) < 500 else "ECHEC",
          "-> {} caracteres".format(len(r.stdout)))

    try:
        s.run("sleep 20", timeout=3)
        print("10) delai : ECHEC (aurait du lever)")
    except SSHTimeout as exc:
        print("10) delai respecte : OK ->", str(exc)[:70])

    # La session a ete tuee par le delai : elle doit repartir toute seule.
    r = s.run("echo relance")
    print("11) reprise apres delai :", r.stdout, "OK" if r.ok else "ECHEC")

    path = "{}/.romeo-mcp-smoke.txt".format(s.scratch)
    s.write_file(path, "ligne 1\nligne $PATH avec 'apostrophes' et \"guillemets\"\n")
    r = s.run("cat {}".format(path))
    ok = "$PATH" in r.stdout and "apostrophes" in r.stdout
    print("12) ecriture fichier sans expansion :", "OK" if ok else "ECHEC")
    print("   ", r.stdout.replace("\n", " | "))
    s.run("rm -f {}".format(path))

    body, trunc = clamp("x" * 100, 50)
    print("13) clamp local :", "OK" if trunc and "omis" in body else "ECHEC")

    s.close()
    print("\ntransport OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
