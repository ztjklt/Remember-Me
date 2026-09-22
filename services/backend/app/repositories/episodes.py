"""Episodes: the capture record and the audio object it points at."""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import EpisodeNotFound
from ..models import Episode, EpisodeStatus
from ..storage.base import StoredObject

# The value sent as `aiCoreInput.existing_model_version` when a subject has no
# ready Episode yet. The contract requires the field to be a non-empty string, so
# absence needs a name; "none" is not a version any model produces.
NO_MODEL_VERSION = "none"


def new_episode_id() -> str:
    return f"ep_{uuid4().hex[:16]}"


def audio_object_key(subject_id: str, episode_id: str) -> str:
    """Where the bytes for one Episode live.

    Built from server-generated ids only. The client's filename never reaches the
    key: it is client-controlled text, which is how a path traversal or an
    unsupported character gets into an object store. What the client called the
    recording is kept as `Episode.audio_ref`, which is a label rather than a
    path.
    """
    return f"audio/{subject_id}/{episode_id}/original"


class EpisodeRepository:
    """Episodes, and the rule that decides who may read one.

    An Episode belongs to the Actor that captured it. `require` is for the worker,
    which acts on behalf of no Actor and addresses Episodes it was handed by the
    queue; every method that answers a *request* is scoped to the Actor making it,
    and an Episode belonging to another Actor is reported exactly as one that does
    not exist, so a response never discloses that another Actor's Episode exists
    (ADR-0001 D7).
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, episode: Episode) -> Episode:
        self.session.add(episode)
        return episode

    def get(self, episode_id: str) -> Episode | None:
        return self.session.get(Episode, episode_id)

    def require(self, episode_id: str) -> Episode:
        """Return the Episode or fail with EPISODE_NOT_FOUND.

        Unscoped on purpose — the worker has no Actor — which is why no request
        handler uses it: see `require_for`.
        """
        episode = self.get(episode_id)
        if episode is None:
            raise EpisodeNotFound(f"No episode with id {episode_id}")
        return episode

    def for_actor(self, episode_id: str, *, actor_id: str) -> Episode | None:
        """The Episode as this Actor may see it, or None when it is not theirs."""
        return self.session.scalars(
            select(Episode).where(
                Episode.episode_id == episode_id,
                Episode.actor_id == actor_id,
            )
        ).one_or_none()

    def require_for(self, episode_id: str, *, actor_id: str) -> Episode:
        """Return the caller's own Episode, or fail EPISODE_NOT_FOUND.

        An Episode captured by another Actor is EPISODE_NOT_FOUND rather than a
        refusal of its own: a distinguishable "exists but is not yours" would let
        one Actor enumerate another's recordings by id.
        """
        episode = self.for_actor(episode_id, actor_id=actor_id)
        if episode is None:
            raise EpisodeNotFound(f"No episode with id {episode_id}")
        return episode

    def find_by_idempotency(
        self, *, subject_id: str, actor_id: str, idempotency_key: str
    ) -> Episode | None:
        """The Episode a previous request with this key created, if any.

        Scoped to (subject, actor) so that one actor's key cannot collide with
        another's, and so a client that derives keys from its own state is safe.
        """
        return self.session.scalars(
            select(Episode).where(
                Episode.subject_id == subject_id,
                Episode.actor_id == actor_id,
                Episode.idempotency_key == idempotency_key,
            )
        ).one_or_none()

    def latest_model_version(self, subject_id: str) -> str:
        """The model version of the subject's most recent ready Episode.

        This is what AI Core is told it is updating, so it must be derived from
        the record rather than supplied by the client.
        """
        version = self.session.scalars(
            select(Episode.model_version)
            .where(
                Episode.subject_id == subject_id,
                Episode.status == str(EpisodeStatus.READY),
                Episode.model_version.is_not(None),
            )
            .order_by(Episode.created_at.desc())
            .limit(1)
        ).one_or_none()
        return version or NO_MODEL_VERSION

    def attach_audio(
        self, episode: Episode, stored: StoredObject, *, audio_ref: str
    ) -> Episode:
        """Record where the bytes went and what they are.

        `stored.checksum` is the digest of what the store actually received, not
        of what the request claimed: the two are compared at the upload boundary.
        """
        episode.audio_ref = audio_ref
        episode.audio_object_key = stored.key
        episode.audio_size_bytes = stored.size_bytes
        episode.audio_content_type = stored.content_type
        episode.audio_checksum = stored.checksum
        return episode