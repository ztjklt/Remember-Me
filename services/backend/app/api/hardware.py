from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..models import Actor
from ..security import current_actor
from ..work3200 import issue_grant

router = APIRouter(prefix='/api/v1/hardware/work3200', tags=['hardware'])


class CredentialRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    device_id: str = Field(pattern=r'^rm-install-[a-f0-9-]{36}$', max_length=47)


@router.post('/credentials')
def credentials(body: CredentialRequest, request: Request, response: Response,
                actor: Actor = Depends(current_actor)) -> dict:
    grant = issue_grant(request.app.state.settings, actor.actor_id, body.device_id)
    response.headers['Cache-Control'] = 'no-store'
    return grant
