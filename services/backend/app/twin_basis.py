"""Version the answer guard without changing raw materials or profile approval."""
import hashlib
from .access import source_basis

ANSWER_GUARD_VERSION = 'twin-grounded-points-v7-history-v1-expression-v2'
GUARD_TAG = 't7h1:'


def from_material_basis(basis):
    digest = hashlib.sha256((ANSWER_GUARD_VERSION+'\0'+basis).encode()).hexdigest()
    return GUARD_TAG + digest[:64-len(GUARD_TAG)]


def is_current_guard(basis):
    return bool(basis and basis.startswith(GUARD_TAG))


def current(session, subject):
    return from_material_basis(source_basis(session, subject))
