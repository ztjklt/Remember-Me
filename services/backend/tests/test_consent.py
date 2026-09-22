import pytest
from sqlalchemy.orm import Session

from app.errors import ConsentInvalid, ConsentRequired
from app.models import Consent, ConsentScope, ConsentStatus, Subject, utcnow
from app.repositories.consents import ConsentRepository
from app.seed import seed_development_data


@pytest.fixture
def seeded(session: Session):
    return seed_development_data(session, subject_name="Ada", actor_name="Ada")


def test_a_granted_recording_consent_authorizes_recording(session, seeded):
    consent = ConsentRepository(session).require_active(
        seeded.consent_id, subject_id=seeded.subject_id, scope=ConsentScope.RECORDING
    )

    assert consent.consent_id == seeded.consent_id
    assert consent.status == ConsentStatus.GRANTED
    assert consent.subject_id == seeded.subject_id
    assert consent.granted_by_actor_id == seeded.actor_id


def test_an_absent_reference_is_consent_required(session, seeded):
    for absent in (None, ""):
        with pytest.raises(ConsentRequired) as error:
            ConsentRepository(session).require_active(
                absent, subject_id=seeded.subject_id, scope=ConsentScope.RECORDING
            )
        assert error.value.code == "CONSENT_REQUIRED"


def test_an_unknown_reference_is_consent_invalid(session, seeded):
    with pytest.raises(ConsentInvalid) as error:
        ConsentRepository(session).require_active(
            "consent_that_does_not_exist",
            subject_id=seeded.subject_id,
            scope=ConsentScope.RECORDING,
        )

    assert error.value.code == "CONSENT_INVALID"


def test_a_revoked_consent_does_not_authorize(session, seeded):
    repository = ConsentRepository(session)
    consent = repository.require_active(
        seeded.consent_id, subject_id=seeded.subject_id, scope=ConsentScope.RECORDING
    )

    repository.revoke(consent)
    session.commit()

    with pytest.raises(ConsentInvalid) as error:
        repository.require_active(
            seeded.consent_id, subject_id=seeded.subject_id, scope=ConsentScope.RECORDING
        )
    assert error.value.code == "CONSENT_INVALID"


def test_a_consent_belonging_to_another_subject_does_not_authorize(session, seeded):
    session.add(Subject(subject_id="subj_other", display_name="Someone else"))
    session.commit()

    with pytest.raises(ConsentInvalid) as error:
        ConsentRepository(session).require_active(
            seeded.consent_id, subject_id="subj_other", scope=ConsentScope.RECORDING
        )

    assert error.value.code == "CONSENT_INVALID"


def test_a_consent_for_another_scope_does_not_authorize_recording(session, seeded):
    """Scope is part of the grant, not a label.

    RECORDING is the only scope Phase 1 registers; Issue #9 introduces the voice
    scope as a separate grant. This proves the mechanism already refuses a
    consent whose scope does not match what is being asked for.
    """
    session.add(
        Consent(
            consent_id="consent_other_scope",
            subject_id=seeded.subject_id,
            granted_by_actor_id=seeded.actor_id,
            scope="VOICE",
            status=ConsentStatus.GRANTED,
            granted_at=utcnow(),
        )
    )
    session.commit()

    repository = ConsentRepository(session)

    with pytest.raises(ConsentInvalid) as error:
        repository.require_active(
            "consent_other_scope",
            subject_id=seeded.subject_id,
            scope=ConsentScope.RECORDING,
        )
    assert error.value.code == "CONSENT_INVALID"

    # The row itself is a valid, granted consent — for its own scope.
    assert repository.find_active(
        "consent_other_scope", subject_id=seeded.subject_id, scope="VOICE"
    ) is not None