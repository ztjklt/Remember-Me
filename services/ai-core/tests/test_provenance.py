import pytest

from app.contracts import load_fixture
from app.errors import EvidenceInvalid
from app.provenance import build_transcript_evidence


def test_build_transcript_evidence_uses_code_point_spans() -> None:
    payload = load_fixture("phase1-happy")
    start = payload.transcript.index("喜欢")
    end = start + len("喜欢周末去爬山")

    evidence = build_transcript_evidence(payload, "evidence-1", start, end, 0.9)

    assert evidence.evidence_id == "evidence-1"
    assert evidence.source_type == "SUBJECT"
    assert evidence.source_ref == f"episode:{payload.episode_id}#span:{start}-{end}"
    assert evidence.excerpt == payload.transcript[start:end]
    assert evidence.span_start == start
    assert evidence.span_end == end
    assert evidence.confidence == 0.9


@pytest.mark.parametrize(
    ("start", "end"),
    [(-1, 2), (2, 1), (0, 10_000)],
)
def test_build_transcript_evidence_rejects_invalid_spans(start: int, end: int) -> None:
    payload = load_fixture("phase1-happy")

    with pytest.raises(EvidenceInvalid, match="transcript span"):
        build_transcript_evidence(payload, "evidence-1", start, end, 0.9)
