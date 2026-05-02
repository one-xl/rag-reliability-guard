from collections.abc import Callable
from pathlib import Path

from fastapi import HTTPException

from app.llm_client import LLMConfigurationError, LLMRequestError
from app.schemas import AnswerEvaluationRequest


def evaluate_answers_payload(
    request: AnswerEvaluationRequest,
    documents_dir: Path,
    evaluate_answer_cases_func: Callable[..., dict],
) -> dict:
    try:
        return evaluate_answer_cases_func(
            request.cases,
            documents_dir,
            method=request.method,
            generator=request.generator,
            top_k=request.top_k,
            min_support_rate=request.min_support_rate,
            min_relevance_overlap=request.min_relevance_overlap,
            continue_on_error=request.continue_on_error,
        )
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMRequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
