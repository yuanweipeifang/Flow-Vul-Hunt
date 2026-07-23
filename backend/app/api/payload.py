from fastapi import APIRouter

from ..schemas import PayloadInspectRequest, PayloadInspectResult
from ..services.payload_inspector import inspect_payload

router = APIRouter(prefix="/payload", tags=["payload"])


@router.post("/inspect", response_model=PayloadInspectResult)
def inspect(request: PayloadInspectRequest) -> dict:
    return inspect_payload(request.payload)
