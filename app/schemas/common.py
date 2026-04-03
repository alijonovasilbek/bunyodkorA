from typing import Generic, TypeVar, Optional
from pydantic import BaseModel


T = TypeVar("T")


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class DataResponse(BaseModel, Generic[T]):
    data: T
    meta: Optional[PaginationMeta] = None
