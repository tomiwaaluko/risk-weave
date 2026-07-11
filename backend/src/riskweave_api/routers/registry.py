from fastapi import APIRouter

router = APIRouter(prefix="/registry", tags=["registry"])


@router.get("/tools")
def tool_registry() -> dict[str, list[str]]:
    return {
        "tools": [
            "run_scenario",
            "propagate_shock",
            "get_propagation_paths",
            "calculate_breach_distance",
        ]
    }
