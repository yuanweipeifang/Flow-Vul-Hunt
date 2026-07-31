from fastapi import APIRouter, Depends

from ..schemas import PayloadInspectRequest, PayloadInspectResult
from ..security import Actor, get_actor
from ..services.payload_inspector import inspect_payload

router = APIRouter(prefix="/payload", tags=["payload"])


@router.post("/inspect", response_model=PayloadInspectResult)
def inspect(request: PayloadInspectRequest, _actor: Actor = Depends(get_actor)) -> dict:
    return inspect_payload(request.payload)
