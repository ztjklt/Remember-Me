import pytest
import sqlalchemy as sa
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


def test_a_grant_for_another_scope_does_not_authorize_recording(session, seeded):
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
        repository.require_active(
            "consent_voice", subject_id=seeded.subject_id, scope=ConsentScope.RECORDING
        )
    assert error.value.code == "CONSENT_INVALID"

    # The row itself is a valid, granted consent — for its own scope.
    assert (
        repository.find_active(
            "consent_voice", subject_id=seeded.subject_id, scope=ConsentScope.VOICE
        )
        is not None
    )


def test_recording_consent_does_not_authorize_a_voice_operation(session, seeded):
    """The boundary Issue #9 draws, stated as the rule rather than as a note.

    seeded carries a granted RECORDING consent for the same subject. A voice
    operation naming the VOICE scope must not be satisfiable by it, and the
    failure must be a validation error rather than a warning.
    """
    with pytest.raises(ConsentInvalid) as error:
        ConsentRepository(session).require_active(
            seeded.consent_id, subject_id=seeded.subject_id, scope=ConsentScope.VOICE
        )

    assert error.value.code == "CONSENT_INVALID"


def test_a_voice_grant_authorizes_the_voice_scope(session, seeded):
    repository = ConsentRepository(session)
    grant = repository.grant(
        subject_id=seeded.subject_id,
        granted_by_actor_id=seeded.actor_id,
        scope=ConsentScope.VOICE,
        evidence_ref="test-fixture",
    )
    session.commit()

    verified = repository.require_active(
        grant.consent_id, subject_id=seeded.subject_id, scope=ConsentScope.VOICE
    )

    assert verified.consent_id == grant.consent_id
    assert verified.scope == str(ConsentScope.VOICE)
    assert verified.granted_by_actor_id == seeded.actor_id
    assert verified.evidence_ref == "test-fixture"


def test_the_two_scopes_are_independent_grants(session, seeded):
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

    assert repository.require_active(
        seeded.consent_id, subject_id=seeded.subject_id, scope=ConsentScope.RECORDING
    ).consent_id == seeded.consent_id
    with pytest.raises(ConsentInvalid):
        repository.require_active(
            voice.consent_id, subject_id=seeded.subject_id, scope=ConsentScope.VOICE
        )


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