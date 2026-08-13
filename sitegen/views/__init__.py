"""Per-view data-preparation modules.

Each module exposes ``build_payload(view, context) -> dict`` returning the
normalized JSON payload written to ``docs/data/<id>.json``. Modules are
registered by ``kind`` so the orchestrator can dispatch without hard-coding
views — adding a view kind means adding a module and one registry entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..reference_tree import ReferenceTree


@dataclass
class BuildContext:
    """Shared state threaded through the topologically-ordered build."""

    root: Path
    data_dir: Path
    trees: dict[str, ReferenceTree] = field(default_factory=dict)


# kind -> builder. Imported lazily to avoid circulars at module load.
def _registry() -> dict[str, Callable[..., dict[str, Any]]]:
    from . import reference

    registry: dict[str, Callable[..., dict[str, Any]]] = {
        "reference": reference.build_payload,
    }
    try:
        from . import population

        registry["population"] = population.build_payload
    except ImportError:
        pass
    try:
        from . import hlca

        registry["hlca"] = hlca.build_payload
    except ImportError:
        pass
    try:
        from . import agreement

        registry["agreement"] = agreement.build_payload
    except ImportError:
        pass
    return registry


def get_builder(kind: str) -> Callable[..., dict[str, Any]]:
    registry = _registry()
    if kind not in registry:
        raise KeyError(f"No data builder registered for view kind '{kind}'.")
    return registry[kind]
