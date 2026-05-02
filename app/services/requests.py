from typing import TypeVar

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from app.schemas import validation_error_detail

TModel = TypeVar("TModel", bound=BaseModel)


def parse_request(model_cls: type[TModel], payload: dict) -> TModel:
    try:
        return model_cls.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=validation_error_detail(exc)) from exc
