"""Owner-scoped short-lived SDK sessions, separate from recording upload grants."""
import time
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from ..access import require_owner
from ..db import get_session
from ..security import current_actor
from ..soundcore_device import authenticate, configured, SDK_VERSION, PRODUCT

router = APIRouter(prefix='/api/v1/subjects/{subject_id}/recording-device')

class DeviceSessionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    installation_id: str = Field(min_length=20, max_length=64, pattern=r'^[a-zA-Z0-9-]+$')

@router.get('/capabilities')
def capabilities(subject_id: str, request: Request, actor=Depends(current_actor), session=Depends(get_session)):
    require_owner(session, subject_id, actor.actor_id)
    return {'available': configured(request.app.state.settings), 'sdk_version': SDK_VERSION, 'product_code': PRODUCT}

@router.post('/session')
def device_session(subject_id: str, body: DeviceSessionInput, request: Request, response: Response,
                   actor=Depends(current_actor), session=Depends(get_session)):
    require_owner(session, subject_id, actor.actor_id)
    cache = getattr(request.app.state, 'soundcore_session_cache', None)
    if cache is None: cache = {}; request.app.state.soundcore_session_cache = cache
    key = (subject_id, actor.actor_id, body.installation_id)
    now = time.time(); prior = cache.get(key)
    if prior and prior[0] > now:
        receipt = prior[1]
    else:
        receipt = authenticate(request.app.state.settings, actor.actor_id, body.installation_id,
                               transport=getattr(request.app.state, 'soundcore_http_transport', None))
        if len(cache) >= 256: cache.pop(next(iter(cache)))
        cache[key] = (min(now + 900, receipt['token_expires_at'] - 60), receipt)
    response.headers['Cache-Control'] = 'no-store'
    return receipt
