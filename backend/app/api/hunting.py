from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import HuntRequest, HuntResult
from ..services.hunt_service import execute_hunt, interpret_hunt


router = APIRouter(prefix="/hunt", tags=["hunting"])


@router.post("/query", response_model=HuntResult)
def hunt(request: HuntRequest, db: Session = Depends(get_db)) -> HuntResult:
    filters, llm_used, warning = interpret_hunt(request.query, request.use_llm)
    events = execute_hunt(db, filters, request.dataset_id, request.limit)
    return HuntResult(
        interpreted_filters=filters.model_dump(exclude_none=True),
        events=events,
        summary=f"查询基于实际数据库返回 {len(events)} 条事件。",
        llm_used=llm_used,
        warning=warning,
    )

