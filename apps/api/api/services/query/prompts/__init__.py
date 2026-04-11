"""Prompt template registry (G-04 / ART-12).

Loads the active template versions from ``config/prompt-config.json`` and
exposes a ``get_template(template_id)`` loader that returns the versioned
module.

Usage:
    from api.services.query.prompts import get_template
    qa = get_template("grounded_qa")   # → grounded_qa_v1 module
    msgs = qa.build_messages(ctx, question)
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

_CONFIG_PATH = Path(__file__).resolve().parents[6] / "config" / "prompt-config.json"

_config: dict[str, str] | None = None
_module_cache: dict[str, ModuleType] = {}


def _load_config() -> dict[str, str]:
    global _config
    if _config is None:
        if _CONFIG_PATH.exists():
            _config = json.loads(_CONFIG_PATH.read_text())
        else:
            _config = {}
    return _config


def get_template(template_id: str) -> ModuleType:
    """Load and return the active version of a prompt template.

    Args:
        template_id: One of "grounded_qa", "query_classify", "recap_summary",
                     "person_context", "embed_preprocess".

    Returns:
        The versioned module (e.g., ``grounded_qa_v1``).

    Raises:
        KeyError: If the template_id is not in prompt-config.json.
        ModuleNotFoundError: If the versioned module doesn't exist.
    """
    if template_id in _module_cache:
        return _module_cache[template_id]

    config = _load_config()
    version = config.get(template_id)
    if version is None:
        raise KeyError(f"Unknown template: '{template_id}'. Check config/prompt-config.json.")

    module_name = f"api.services.query.prompts.{template_id}_{version}"
    mod = importlib.import_module(module_name)
    _module_cache[template_id] = mod
    return mod
