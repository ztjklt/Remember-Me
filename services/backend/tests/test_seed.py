import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import SubjectNotFound
from app.models import Consent, ConsentScope, ConsentStatus, utcnow
from app.repositories.actors import ActorRepository
from app.repositories.consents import ConsentRepository
from app.repositories.subjects import SubjectRepository
from app.seed import seed_development_data


def test_seed_persists_a_subject_an_actor_and_a_consent(session: Session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")

    subject = SubjectRepository(session).require(seeded.subject_id)
    actor = ActorRepository(session).require(seeded.actor_id)
    consent = session.get(Consent, seeded.consent_id)

    assert subject.display_name == "Ada"
    assert actor.display_name == "Ada"
    assert consent is not None


def test_the_seeded_record_satisfies_the_foundation_statement(session: Session):
    """Issue #8's definition of done, asserted rather than described."""
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")

    consent = ConsentRepository(session).require_active(
        seeded.consent_id,
        subject_id=seeded.subject_id,
        scope=ConsentScope.RECORDING,
        actor_id=seeded.actor_id,
    )

    assert consent.subject_id == seeded.subject_id
    assert consent.granted_by_actor_id == seeded.actor_id
    assert consent.status == ConsentStatus.GRANTED


def test_the_seeded_token_authenticates_its_actor(session: Session):
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")

    actor = ActorRepository(session).find_by_token(seeded.actor_token)

    assert actor is not None
    assert actor.actor_id == seeded.actor_id


def test_a_wrong_token_resolves_to_nothing(session: Session):
    seed_development_data(session, subject_name="Ada", actor_name="Ada")

    assert ActorRepository(session).find_by_token("not-the-token") is None


def test_seeding_twice_creates_distinct_records(session: Session):
    first = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    second = seed_development_data(session, subject_name="Ada", actor_name="Ada")

    assert first.subject_id != second.subject_id
    assert first.actor_id != second.actor_id
    assert first.consent_id != second.consent_id
    assert first.actor_token != second.actor_token


def test_a_subject_with_a_consent_cannot_be_deleted(session: Session):
    """Foreign keys are RESTRICT, and SQLite only enforces them when asked to."""
    seeded = seed_development_data(session, subject_name="Ada", actor_name="Ada")
    subject = SubjectRepository(session).require(seeded.subject_id)

    session.delete(subject)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    assert session.get(Consent, seeded.consent_id) is not None


def test_an_unknown_subject_is_reported_as_not_found(session: Session):
    with pytest.raises(SubjectNotFound) as error:
        SubjectRepository(session).require("subj_that_does_not_exist")

    assert error.value.code == "SUBJECT_NOT_FOUND"


def test_a_consent_must_reference_an_existing_subject(session: Session):
    session.add(
        Consent(
            consent_id="consent_orphan",
            subject_id="subj_that_does_not_exist",
            granted_by_actor_id="actor_that_does_not_exist",
            scope=str(ConsentScope.RECORDING),
            status=str(ConsentStatus.GRANTED),
            granted_at=utcnow(),
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()