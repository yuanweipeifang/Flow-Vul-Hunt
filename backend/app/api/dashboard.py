from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Dataset
from ..schemas import DashboardOverview
from ..services.dashboard_service import dashboard_overview

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverview)
def overview(dataset_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    if dataset_id and not db.get(Dataset, dataset_id):
        raise HTTPException(status_code=404, detail="dataset not found")
    return dashboard_overview(db, dataset_id)
