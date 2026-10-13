from sqlalchemy import select
from sqlalchemy.orm import Session

from ..errors import SubjectNotFound
from ..models import Subject


class SubjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, subject: Subject) -> Subject:
        self.session.add(subject)
        return subject

    def get(self, subject_id: str) -> Subject | None:
        return self.session.get(Subject, subject_id)

    def require(self, subject_id: str) -> Subject:
        """Return the subject or fail with SUBJECT_NOT_FOUND."""
        subject = self.get(subject_id)
        if subject is None:
            raise SubjectNotFound(f"No subject with id {subject_id}")
        return subject

    def list_all(self) -> list[Subject]:
        return list(self.session.scalars(select(Subject).order_by(Subject.created_at)))