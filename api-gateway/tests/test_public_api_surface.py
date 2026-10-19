from __future__ import annotations

import json
from pathlib import Path

from app.services.auth import PUBLIC_PREFIXES
from app.services.routing import ROUTE_TABLE

_MANIFEST = Path(__file__).parent / "public_api_surface.json"


def _current_surface() -> dict[str, list[str]]:
    return {
        "proxied_prefixes": sorted(ROUTE_TABLE),
        "unauthenticated_prefixes": sorted(PUBLIC_PREFIXES),
    }


def test_public_api_surface_matches_manifest():
    expected = json.loads(_MANIFEST.read_text())
    actual = _current_surface()
    assert actual == expected, (
        "Public API surface drifted from the reviewed baseline. If this change is "
        f"intentional, update {_MANIFEST.name} in the same PR so a reviewer signs off "
        f"on the new surface.\nexpected={expected}\nactual={actual}"
    )
