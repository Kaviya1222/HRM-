from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_current_auth_context, get_db
from app.schemas.search import GlobalSearchResponse
from app.services.search_service import SearchService

router = APIRouter()


@router.get("/global", response_model=GlobalSearchResponse)
def global_search(
    q: str = Query(min_length=2, max_length=100),
    limit_per_module: int = Query(default=4, ge=1, le=8),
    auth: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return SearchService.global_search(
        db,
        auth,
        query=q,
        limit_per_module=limit_per_module,
    )
