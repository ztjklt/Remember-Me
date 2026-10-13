from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.errors import ConsentInvalid, ConsentNotFound, ConsentRequired
from app.models import Actor, Consent, ConsentScope, ConsentStatus, Subject, utcnow
from app.repositories.consents import ConsentRepository
from app.seed import seed_development_data
from app.tokens import generate_actor_token, hash_actor_token


@pytest.fixture
def seeded(session: Session):
    return seed_development_data(session, subject_name="Ada", actor_name="Ada")


@pytest.fixture
def other_actor(session: Session) -> str:
    """A second Actor, so a grant can belong to somebody other than the caller."""
    actor = Actor(
        actor_id=f"actor_{uuid4().hex[:16]}",
        display_name="Bob",
        token_hash=hash_actor_token(generate_actor_token()),
    )
    session.add(actor)
    session.commit()
    return actor.actor_id


@pytest.fixture
def verify(session: Session, seeded):
    """Ask the verification rule as the seeding Actor unless told otherwise.

    `actor_id` is a parameter rather than a default the repository applies,
    because the rule under test is *whose* grant it is.
    """

    def ask(consent_id, *, scope=ConsentScope.RECORDING, subject_id=None, actor_id=None):
        return ConsentRepository(session).require_active(
            consent_id,
            subject_id=subject_id or seeded.subject_id,
            scope=scope,
            actor_id=actor_id or seeded.actor_id,
        )

    return ask


def test_a_granted_recording_consent_authorizes_recording(verify, seeded):
    consent = verify(seeded.consent_id)

    assert consent.consent_id == seeded.consent_id
    assert consent.status == ConsentStatus.GRANTED
    assert consent.subject_id == seeded.subject_id
    assert consent.granted_by_actor_id == seeded.actor_id


def test_an_absent_reference_is_consent_required(verify):
    for absent in (None, ""):
        with pytest.raises(ConsentRequired) as error:
            verify(absent)
        assert error.value.code == "CONSENT_REQUIRED"


def test_an_unknown_reference_is_reported_as_absent(verify):
    """An id that was never granted is CONSENT_NOT_FOUND, not CONSENT_INVALID.

    The rule reads "a consent this actor holds", so a reference nobody holds and
    a reference another actor holds have to answer identically — see
    `test_another_actors_grant_answers_exactly_like_one_that_does_not_exist`.
    """
    with pytest.raises(ConsentNotFound) as error:
        verify("consent_that_does_not_exist")

    assert error.value.code == "CONSENT_NOT_FOUND"


def test_a_revoked_consent_does_not_authorize(session, seeded, verify):
    repository = ConsentRepository(session)
    repository.revoke(verify(seeded.consent_id))
    session.commit()

    with pytest.raises(ConsentInvalid) as error:
        verify(seeded.consent_id)
    assert error.value.code == "CONSENT_INVALID"


def test_a_consent_belonging_to_another_subject_does_not_authorize(session, seeded, verify):
    session.add(Subject(subject_id="subj_other", display_name="Someone else"))
    session.commit()

    with pytest.raises(ConsentInvalid) as error:
        verify(seeded.consent_id, subject_id="subj_other")

    assert error.value.code == "CONSENT_INVALID"


def test_a_grant_for_another_scope_does_not_authorize_recording(session, seeded, verify):
    """Scope is part of the grant, not a label on it.

    Both scopes are registered, so this is the separation itself rather than a
    placeholder for it: a VOICE grant does not authorize RECORDING.
    """
    session.add(
        Consent(
            consent_id="consent_voice",
            subject_id=seeded.subject_id,
            granted_by_actor_id=seeded.actor_id,
            scope=str(ConsentScope.VOICE),
            status=ConsentStatus.GRANTED,
            granted_at=utcnow(),
        )
    )
    session.commit()

    repository = ConsentRepository(session)

    with pytest.raises(ConsentInvalid) as error:
        verify("consent_voice")
    assert error.value.code == "CONSENT_INVALID"

    # The row itself is a valid, granted consent — for its own scope.
    assert repository.for_actor("consent_voice", actor_id=seeded.actor_id) is not None


def test_recording_consent_does_not_authorize_a_voice_operation(seeded, verify):
    """The boundary Issue #9 draws, stated as the rule rather than as a note.

    seeded carries a granted RECORDING consent for the same subject. A voice
    operation naming the VOICE scope must not be satisfiable by it, and the
    failure must be a validation error rather than a warning.
    """
    with pytest.raises(ConsentInvalid) as error:
        verify(seeded.consent_id, scope=ConsentScope.VOICE)

    assert error.value.code == "CONSENT_INVALID"


def test_a_voice_grant_authorizes_the_voice_scope(session, seeded, verify):
    repository = ConsentRepository(session)
    grant = repository.grant(
        subject_id=seeded.subject_id,
        granted_by_actor_id=seeded.actor_id,
        scope=ConsentScope.VOICE,
        evidence_ref="test-fixture",
    )
    session.commit()

    verified = verify(grant.consent_id, scope=ConsentScope.VOICE)

    assert verified.consent_id == grant.consent_id
    assert verified.scope == str(ConsentScope.VOICE)
    assert verified.granted_by_actor_id == seeded.actor_id
    assert verified.evidence_ref == "test-fixture"


def test_the_two_scopes_are_independent_grants(session, seeded, verify):
    """Granting voice does not revoke or alter recording, and vice versa."""
    repository = ConsentRepository(session)
    voice = repository.grant(
        subject_id=seeded.subject_id,
        granted_by_actor_id=seeded.actor_id,
        scope=ConsentScope.VOICE,
    )
    session.commit()

    repository.revoke(voice)
    session.commit()

    assert verify(seeded.consent_id).consent_id == seeded.consent_id
    with pytest.raises(ConsentInvalid):
        verify(voice.consent_id, scope=ConsentScope.VOICE)


def test_another_actors_grant_is_never_usable(seeded, other_actor, verify, session):
    """The authorization rule, with subject and scope held constant.

    The grant below is for the same subject and the same scope as the one the
    caller holds; the only difference is which Actor made it. That is the whole
    rule, so the test would pass for the wrong reason if the subject differed.
    """
    repository = ConsentRepository(session)
    theirs = repository.grant(
        subject_id=seeded.subject_id,
        granted_by_actor_id=other_actor,
        scope=ConsentScope.VOICE,
    )
    session.commit()

    with pytest.raises(ConsentNotFound) as error:
        verify(theirs.consent_id, scope=ConsentScope.VOICE)
    assert error.value.code == "CONSENT_NOT_FOUND"

    # A legacy self-granted record no longer creates ownership.
    from app.access import Hidden
    with pytest.raises(Hidden):
        verify(theirs.consent_id, scope=ConsentScope.VOICE, actor_id=other_actor)


def test_another_actors_grant_answers_exactly_like_one_that_does_not_exist(
    seeded, other_actor, verify
):
    """The two refusals are one answer, so neither can be used as a probe.

    If an id belonging to another Actor answered differently from an id nobody
    holds, an Actor could discover other Actors' grants by asking.
    """
    with pytest.raises(ConsentNotFound) as unknown:
        verify("consent_that_does_not_exist")
    with pytest.raises(ConsentNotFound) as someone_elses:
        verify(seeded.consent_id, actor_id=other_actor)

    assert unknown.value.code == someone_elses.value.code == "CONSENT_NOT_FOUND"


def test_a_consent_record_cannot_be_read_across_actors(session, seeded, other_actor):
    repository = ConsentRepository(session)

    assert (
        repository.require_for(seeded.consent_id, actor_id=seeded.actor_id).consent_id
        == seeded.consent_id
    )
    assert repository.for_actor(seeded.consent_id, actor_id=other_actor) is None
    with pytest.raises(ConsentNotFound):
        repository.require_for(seeded.consent_id, actor_id=other_actor)


def test_listing_returns_only_the_callers_own_grants(session, seeded, other_actor):
    """Another actor's grants for the same subject are filtered, not reported."""
    repository = ConsentRepository(session)
    repository.grant(
        subject_id=seeded.subject_id,
        granted_by_actor_id=other_actor,
        scope=ConsentScope.VOICE,
    )
    session.commit()

    mine = repository.list_for_actor(seeded.subject_id, actor_id=seeded.actor_id)
    theirs = repository.list_for_actor(seeded.subject_id, actor_id=other_actor)

    assert [consent.consent_id for consent in mine] == [seeded.consent_id]
    assert [consent.scope for consent in theirs] == [str(ConsentScope.VOICE)]


def test_the_database_refuses_a_scope_this_codebase_does_not_register(session, seeded):
    """The registered scopes are enforced by the database, not only by the enum.

    A row written by hand, by a future migration, or by another service cannot
    create a grant that no verification rule would ever match.
    """
    with pytest.raises(sa.exc.IntegrityError):
        session.execute(
            sa.text(
                "INSERT INTO consents (consent_id, subject_id, granted_by_actor_id,"
                " scope, status, granted_at, created_at)"
                " VALUES ('consent_typo', :subject_id, :actor_id, 'RECORDNG',"
                " 'granted', :now, :now)"
            ),
            {
                "subject_id": seeded.subject_id,
                "actor_id": seeded.actor_id,
                "now": utcnow(),
            },
        )
        session.flush()
    session.rollback()
