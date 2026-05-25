from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_db, require_permissions
from app.services.dashboard_service import DashboardService

router = APIRouter()


@router.get("/summary")
def get_dashboard_summary(
    auth: AuthContext = Depends(require_permissions("page.dashboard.view")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return DashboardService.summary(db, auth)
