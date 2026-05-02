"""Pydantic request models for API boundary validation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
)


class _ApiModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class AnswerRequest(_ApiModel):
    question: str
    top_k: StrictInt = Field(default=5, ge=1, le=20)
    method: Literal["keyword", "bm25"] = "keyword"
    generator: Literal["extractive", "doubao"] = "extractive"
    min_support_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    min_relevance_overlap: float | None = Field(default=None, ge=0.0, le=1.0)
    fallback_to_extractive: StrictBool = True

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must be a non-empty string")
        return value


class AnswerEvaluationRequest(_ApiModel):
    cases: list[dict[str, Any]]
    method: Literal["keyword", "bm25"] = "keyword"
    generator: Literal["extractive", "doubao"] = "extractive"
    top_k: StrictInt = Field(default=5, ge=1, le=20)
    min_support_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    min_relevance_overlap: float | None = Field(default=None, ge=0.0, le=1.0)
    continue_on_error: StrictBool = False
    save: StrictBool = False


class ExternalAnswerRequest(_ApiModel):
    case_id: str | None = None
    question: str
    answer: str
    answerable: StrictBool
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    model: str | None = None
    provider: str | None = None
    run_id: str | None = None
    min_support_rate: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must be a non-empty string")
        return value


class ExternalAnswerBatchRequest(_ApiModel):
    cases: list[dict[str, Any]]
    min_support_rate: float | None = Field(default=None, ge=0.0, le=1.0)


def validation_error_detail(exc: ValidationError) -> str:
    """Compact Pydantic errors into the existing string-detail 400 style."""
    first = exc.errors()[0]
    loc = ".".join(str(part) for part in first.get("loc", ())) or "payload"
    msg = first.get("msg", "invalid value")
    return f"{loc}: {msg}"
