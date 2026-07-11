from fastapi import Request

from riskweave_api.scenario_store import ScenarioStore


def get_store(request: Request) -> ScenarioStore:
    return request.app.state.store
