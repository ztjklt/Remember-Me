from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..models import Actor
from ..security import current_actor

router = APIRouter(prefix="/api/v1", tags=["auth"])


class SessionResponse(BaseModel):
    actor_id: str
    display_name: str


@router.get("/session", response_model=SessionResponse)
def read_session(actor: Actor = Depends(current_actor)) -> SessionResponse:
    """Return the Actor the presented token authenticates.

    This is the whole of the Phase 1 auth boundary: it proves the token-to-Actor
    resolution that attributes Episodes to an Actor in Issue #1. It is not
    production authentication.
    """
    return SessionResponse(actor_id=actor.actor_id, display_name=actor.display_name)