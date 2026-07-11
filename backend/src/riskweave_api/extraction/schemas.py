from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PassageLocation(StrictModel):
    source_document_id: str = Field(description="Immutable source document identifier.")
    char_start: int = Field(ge=0, description="Chunk-local start offset for source_passage.")
    char_end: int = Field(ge=0, description="Chunk-local exclusive end offset for source_passage.")


class RelationshipExtraction(StrictModel):
    source_entity: str = Field(min_length=1)
    target_entity: str = Field(min_length=1)
    relationship_type: str = Field(min_length=1)
    direction: Literal["positive", "negative"]
    disclosed_magnitude: str | None
    source_passage: str = Field(min_length=1)
    passage_location: PassageLocation
    extraction_confidence: float = Field(ge=0, le=1)


class RelationshipExtractionBatch(StrictModel):
    relationships: list[RelationshipExtraction]


class CovenantThresholdExtraction(StrictModel):
    entity: str = Field(min_length=1)
    covenant_type: Literal[
        "leverage_limit",
        "interest_coverage_minimum",
        "minimum_liquidity",
    ]
    threshold_value: str = Field(min_length=1)
    source_passage: str = Field(min_length=1)
    passage_location: PassageLocation
    extraction_confidence: float = Field(ge=0, le=1)


class CovenantThresholdExtractionBatch(StrictModel):
    covenants: list[CovenantThresholdExtraction]


def relationship_response_schema() -> dict[str, object]:
    return RelationshipExtractionBatch.model_json_schema()


def covenant_response_schema() -> dict[str, object]:
    return CovenantThresholdExtractionBatch.model_json_schema()
