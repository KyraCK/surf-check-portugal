"""Abrufe im Netz: mit Zeitlimit, Wiederholung und verständlichem Fehlertext."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

USER_AGENT = "surf-check-portugal/1.0 (privates Projekt, nicht kommerziell)"


class AbrufFehler(Exception):
    """Eine Quelle hat nicht geantwortet oder Unbrauchbares geliefert."""


def hole_json(url: str, versuche: int = 3, timeout: int = 30):
    """Lädt JSON. Gibt None zurück, wenn die Quelle bewusst nichts liefert (HTTP 204)."""
    letzter = "unbekannter Fehler"
    for i in range(versuche):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if r.status == 204:
                    return None
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            letzter = f"HTTP {e.code}"
            if 400 <= e.code < 500 and e.code != 429:
                break  # Wiederholen hilft bei "nicht gefunden" nicht
        except Exception as e:  # Zeitüberschreitung, DNS, kaputtes JSON ...
            letzter = f"{type(e).__name__}: {e}"
        if i < versuche - 1:
            time.sleep(2 * (i + 1))
    raise AbrufFehler(letzter)
