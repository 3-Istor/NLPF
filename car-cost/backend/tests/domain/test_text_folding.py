"""Le pliage du texte : la table de cas est partagée avec le front."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from carcost.domain.text_folding import fold

CASES = json.loads(
    (Path(__file__).resolve().parents[1] / "fold_cases.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", CASES, ids=[c["input"] or "vide" for c in CASES])
def test_fold_matches_the_shared_table(case):
    assert fold(case["input"]) == case["folded"]
