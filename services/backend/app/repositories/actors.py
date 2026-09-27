from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import ActorNotFound
from ..models import Actor, DeviceCredential
from ..tokens import hash_actor_token


class ActorRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, actor: Actor) -> Actor:
        self.session.add(actor)
        return actor

    def get(self, actor_id: str) -> Actor | None:
        return self.session.get(Actor, actor_id)

    def require(self, actor_id: str) -> Actor:
        """Return the actor or fail with ACTOR_NOT_FOUND."""
        actor = self.get(actor_id)
        if actor is None:
            raise ActorNotFound(f"No actor with id {actor_id}")
        return actor

    def find_by_token(self, token: str) -> Actor | None:
        """Resolve a presented actor token to its actor, or None.

        The token itself is never stored; lookup is by digest.
        """
        actor = self.session.scalars(
            select(Actor).where(Actor.token_hash == hash_actor_token(token))
        ).one_or_none()
        if actor is not None:
            return actor
        credential = self.session.get(DeviceCredential, hash_actor_token(token))
        return self.session.get(Actor, credential.actor_id) if credential else None
