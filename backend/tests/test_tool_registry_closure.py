"""RW-SEC-002 / RW-AI-002: the Gemini tool registry (spec §13.2) is closed.

Gemini orchestration may only call the deterministic functions registered in
spec §13.2; arbitrary tool execution is prohibited. The registry router in
``riskweave_api.routers.registry`` is that closed surface. These tests pin the
exposed tool set to the exact §13.2 list so that adding, renaming, or removing
a tool fails CI and forces an explicit review (ADR/PDR) rather than silently
widening what Gemini can invoke.
"""

from __future__ import annotations

from riskweave_api.routers import registry

# The closed §13.2 registry: each registry-router endpoint mapped to its spec
# tool name. This is the *only* set of functions Gemini function-calling may
# reach. Nothing outside this set is permitted (RW-SEC-002).
EXPECTED_TOOL_REGISTRY: dict[str, str] = {
    "resolve_entity": "resolve_entity",
    "get_company_exposures": "get_company_exposures",
    "run_scenario_registry": "run_scenario",
    "propagate_shock": "propagate_shock",
    "get_propagation_paths": "get_propagation_paths",
    "breach_distance": "calculate_breach_distance",
    "duration_transmission": "calculate_duration",
    "get_ratio": "get_ratio",
    "retrieve_filing_passage": "retrieve_filing_passage",
    "retrieve_fred_series": "retrieve_fred_series",
}


def _exposed_tool_names() -> set[str]:
    return {route.name for route in registry.router.routes}


def test_tool_registry_exposes_exactly_the_closed_section_13_2_set() -> None:
    """The registry router exposes the §13.2 tools and nothing more (RW-SEC-002).

    A new endpoint added to the registry router (i.e. a new tool handed to
    Gemini) must be a deliberate, reviewed change to this closed set — not an
    accident. Extra or missing tools both fail here.
    """
    exposed = _exposed_tool_names()
    expected = set(EXPECTED_TOOL_REGISTRY)

    unregistered = exposed - expected
    assert not unregistered, (
        f"registry router exposes tools outside the closed §13.2 set: {sorted(unregistered)}; "
        "adding a Gemini-callable tool requires an ADR/PDR (RW-SEC-002)"
    )

    missing = expected - exposed
    assert not missing, f"closed §13.2 tools missing from the registry router: {sorted(missing)}"


def test_tool_registry_covers_every_spec_section_13_2_tool() -> None:
    """Every tool named in spec §13.2 is accounted for in the closed registry."""
    spec_section_13_2_tools = {
        "resolve_entity",
        "get_company_exposures",
        "run_scenario",
        "propagate_shock",
        "get_propagation_paths",
        "calculate_breach_distance",
        "calculate_duration",
        "get_ratio",
        "retrieve_filing_passage",
        "retrieve_fred_series",
    }
    assert set(EXPECTED_TOOL_REGISTRY.values()) == spec_section_13_2_tools


def test_registry_router_has_no_undocumented_prefix_leak() -> None:
    """Every exposed registry route lives under the ``/registry`` prefix."""
    for route in registry.router.routes:
        assert route.path.startswith("/registry/"), (
            f"registry tool {route.name!r} escapes the /registry prefix: {route.path}"
        )
