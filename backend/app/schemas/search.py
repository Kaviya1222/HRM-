from __future__ import annotations

from pydantic import BaseModel, Field


class SearchResultItem(BaseModel):
    id: str
    module: str
    title: str
    subtitle: str
    description: str | None = None
    path: str


class SearchResultSection(BaseModel):
    module: str
    label: str
    path: str
    items: list[SearchResultItem] = Field(default_factory=list)


class GlobalSearchResponse(BaseModel):
    query: str
    total_results: int
    sections: list[SearchResultSection] = Field(default_factory=list)
