"""Tests for the versioned derivation-method registry (spec §12.1)."""

from __future__ import annotations

import pytest

from riskweave.derivations import (
    REGISTRY,
    UnknownMethodError,
    get_method,
    list_methods,
)

EXPECTED_IDS = {
    "DER-COMMODITY",
    "DER-CONCENTRATION",
    "DER-CREDIT",
    "DER-DURATION",
    "DER-GEO",
    "DER-BETA",
}


def test_all_six_methods_registered():
    assert set(REGISTRY) == EXPECTED_IDS
    assert len(list_methods()) == 6


def test_every_method_is_versioned_with_spec_row():
    for method in list_methods():
        assert method.version, f"{method.method_id} missing version"
        assert method.spec_row, f"{method.method_id} missing spec row"
        assert method.source_data
        assert method.variants


def test_get_method_returns_metadata():
    method = get_method("DER-BETA")
    assert method.method_id == "DER-BETA"
    assert "beta" in method.summary.lower()


def test_unknown_method_raises():
    with pytest.raises(UnknownMethodError):
        get_method("DER-NONEXISTENT")


def test_registry_is_read_only():
    with pytest.raises(TypeError):
        REGISTRY["DER-NEW"] = None  # type: ignore[index]
