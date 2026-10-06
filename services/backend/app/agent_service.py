"""Trusted orchestration: authorization, material resolver, snapshots, CAS and locks."""

from hashlib import sha256
import json
import re
from uuid import uuid4
from sqlalchemy import exists, select, update
from remember_contracts.agent import (
    CalibrationView,
    CompareInput,
    Material,
    PersonaInput,
    Plan,
    Snapshot,
    TwinAnswer,
    TwinInput,
)
from .errors import AppError, AiSchemaInvalid, ConsentInvalid, RequestInvalid
from .models import (
    AgentMaterial,
    AgentRevision,
    AgentState,
    CalibrationRecord,
    Consent,
    ConsentScope,
    Episode,
    Evidence,
    MemoryItem,
    as_utc,
    utcnow,
)
from .repositories.consents import ConsentRepository


class AgentConflict(AppError):
    code = "AGENT_REVISION_CONFLICT"
    http_status = 409
    retryable = True


class AgentNotFound(AppError):
    code = "AGENT_NOT_FOUND"
    http_status = 404


class AgentService:
    def __init__(self, session, client):
        self.session = session
        self.client = client

    @staticmethod
    def key(subject_id, actor_id):
        return (
            "agent_" + sha256((subject_id + "\0" + actor_id).encode()).hexdigest()[:40]
        )

    def grant(self, subject_id, actor_id, request):
        ConsentRepository(self.session).require_active(
            request.recording_consent_id,
            subject_id=subject_id,
            scope=ConsentScope.RECORDING,
            actor_id=actor_id,
        )
        key = self.key(subject_id, actor_id)
        state = self.session.get(AgentState, key)
        if state is None:
            state = AgentState(
                state_id=key,
                subject_id=subject_id,
                actor_id=actor_id,
                recording_consent_id=request.recording_consent_id,
                active=True,
                generation=uuid4().hex,
                revision=0,
                excluded_episode_ids=[],
            )
            self.session.add(state)
        elif (
            not state.active
            or state.recording_consent_id != request.recording_consent_id
        ):
            state.active = True
            state.recording_consent_id = request.recording_consent_id
            state.generation = uuid4().hex
            state.granted_at = utcnow()
            state.revoked_at = None
        self.session.commit()
        return {
            "subject_id": subject_id,
            "active": True,
            "speaker_authority": "SELF_ATTESTED",
            "revision": state.revision,
        }

    def require(self, subject_id, actor_id):
        state = self.session.get(AgentState, self.key(subject_id, actor_id))
        if state is None:
            raise AgentNotFound("No Agent session for this Subject")
        if not state.active:
            raise ConsentInvalid("Cloud Twin consent has been revoked")
        ConsentRepository(self.session).require_active(
            state.recording_consent_id,
            subject_id=subject_id,
            scope=ConsentScope.RECORDING,
            actor_id=actor_id,
        )
        return state

    def guard(self, state, expected_revision=None):
        current = self.session.execute(
            select(AgentState.active, AgentState.generation, AgentState.revision).where(
                AgentState.state_id == state.state_id
            )
        ).one()
        if not current.active or current.generation != state.generation:
            raise ConsentInvalid("Cloud Twin consent changed during processing")
        consent = self.session.execute(
            select(Consent.status, Consent.revoked_at).where(
                Consent.consent_id == state.recording_consent_id
            )
        ).one()
        if consent.status != "granted" or consent.revoked_at is not None:
            raise ConsentInvalid("Recording consent changed during processing")
        if expected_revision is not None and current.revision != expected_revision:
            raise AgentConflict("Persona changed during processing; refresh and retry")

    def revoke(self, state):
        state.active = False
        state.generation = uuid4().hex
        state.revoked_at = utcnow()
        self.session.commit()

    def materials(self, state, include_episode_id=None):
        rows = self.session.execute(
            select(Evidence, Episode)
            .join(Episode, Evidence.episode_id == Episode.episode_id)
            .join(Consent, Episode.recording_consent_id == Consent.consent_id)
            .where(
                Episode.subject_id == state.subject_id,
                Episode.actor_id == state.actor_id,
                Consent.status == "granted",
                Consent.revoked_at.is_(None),
                (Episode.status == "ready")
                | (Episode.episode_id == include_episode_id),
            )
            .order_by(Episode.recorded_at, Evidence.evidence_id)
        ).all()
        material_list = []
        types = {}
        for item in self.session.scalars(
            select(MemoryItem)
            .join(Episode)
            .where(
                Episode.subject_id == state.subject_id,
                Episode.actor_id == state.actor_id,
            )
        ):
            for eid in item.evidence_ids:
                types.setdefault(eid, item.memory_type)
        for evidence, episode in rows:
            if (
                episode.episode_id in state.excluded_episode_ids
                or (episode.capture_metadata or {}).get("agent_subject_single_speaker")
                is not True
            ):
                continue
            if (
                evidence.source_type != "SUBJECT"
                or evidence.excerpt is None
                or not episode.transcript
            ):
                continue
            start, end = evidence.span_start, evidence.span_end
            if (
                start is None
                or end is None
                or start < 0
                or start >= end
                or end > len(episode.transcript)
            ):
                continue
            if (
                episode.transcript[start:end] != evidence.excerpt
                or evidence.source_ref
                != f"episode:{episode.episode_id}#span:{start}-{end}"
            ):
                continue
            material_list.append(
                Material(
                    evidence_id=evidence.evidence_id,
                    episode_id=episode.episode_id,
                    excerpt=evidence.excerpt,
                    source_type="THIRD_PARTY"
                    if re.search(
                        r"(?:女儿|儿子|朋友|医生|同事|妈妈|爸爸|他|她)(?:说|觉得|认为)[：:，,]?",
                        evidence.excerpt,
                    )
                    else "SUBJECT",
                    source_ref=evidence.source_ref,
                    memory_type=types.get(evidence.evidence_id, "EVENT"),
                    observed_at=as_utc(episode.recorded_at),
                    speaker_authority="SELF_ATTESTED",
                )
            )
        # Original text is a first-class input, independent of which spans the
        # unchanged Memory extractor selected. Reuse full-span evidence when present.
        episodes = self.session.scalars(select(Episode).join(Consent).where(
            Episode.subject_id == state.subject_id, Episode.actor_id == state.actor_id,
            Consent.status == "granted", Consent.revoked_at.is_(None),
            (Episode.status == "ready") | (Episode.episode_id == include_episode_id),
        ).order_by(Episode.recorded_at, Episode.episode_id))
        for episode in episodes:
            text = episode.transcript
            if (not text or episode.episode_id in state.excluded_episode_ids
                or (episode.capture_metadata or {}).get("agent_subject_single_speaker") is not True):
                continue
            source_ref = f"episode:{episode.episode_id}#span:0-{len(text)}"
            if any(m.source_ref == source_ref for m in material_list):
                continue
            if len(text) > 12000:
                raise RequestInvalid("Original transcript exceeds experimental context budget; no text was truncated")
            material_list.append(Material(
                evidence_id="tr_" + sha256((episode.episode_id + "\0" + text).encode()).hexdigest()[:40],
                episode_id=episode.episode_id, excerpt=text, source_ref=source_ref,
                source_type="THIRD_PARTY" if re.search(
                    r"(?:女儿|儿子|朋友|医生|同事|妈妈|爸爸|他|她)(?:说|觉得|认为)[：:，,]?", text
                ) else "SUBJECT",
                observed_at=as_utc(episode.recorded_at), speaker_authority="SELF_ATTESTED",
            ))
        original_ids = {m.evidence_id for m in material_list}
        for item in self.session.scalars(
            select(AgentMaterial)
            .where(AgentMaterial.state_id == state.state_id)
            .order_by(AgentMaterial.observed_at)
        ):
            record = self.session.get(CalibrationRecord, item.calibration_id)
            if (
                record.state == "INVALIDATED"
                or not set(record.locked_answer["evidence_ids"]) <= original_ids
            ):
                continue
            material_list.append(
                Material(
                    evidence_id=item.evidence_id,
                    excerpt=item.excerpt,
                    source_type="CALIBRATION",
                    source_ref="calibration:" + item.calibration_id,
                    observed_at=as_utc(item.observed_at),
                    context=item.context,
                    speaker_authority="SELF_ATTESTED",
                )
            )
            original_ids.add(item.evidence_id)
        if len(material_list) > 160:
            raise RequestInvalid(
                "Experimental Agent material budget exceeded (160); export or reduce demo materials"
            )
        return material_list

    def snapshot(self, state, materials=None):
        snapshot = (
            Snapshot.model_validate(state.snapshot)
            if state.snapshot
            else Snapshot(
                subject_id=state.subject_id,
                revision=0,
                model_version="uninitialized",
                prompt_version="agent-workers-v1",
                limitations=[
                    "本人来源为操作人声明，未完成身份或说话人认证。",
                    "人格理解是有证据的候选，不是完整人格复刻。",
                ],
            )
        )
        if materials is None:
            materials = self.materials(state)
        allowed = {
            m.evidence_id
            for m in materials
            if m.source_type in {"SUBJECT", "CALIBRATION"}
            and m.speaker_authority == "SELF_ATTESTED"
        }
        # Source revocation also invalidates historical projections on read.
        traits = []
        for t in snapshot.traits:
            if set(t.evidence_ids + t.counter_evidence_ids) <= allowed:
                traits.append(t)
        return snapshot.model_copy(update={"traits": traits})

    def processed(self, state):
        revision = self.session.get(AgentRevision, f"{state.state_id}:{state.revision}")
        return set(revision.processed_evidence_ids) if revision else set()

    def validate_persona(self, result, state, snapshot, materials):
        allowed = {
            m.evidence_id
            for m in materials
            if m.source_type in {"SUBJECT", "CALIBRATION"}
            and m.speaker_authority == "SELF_ATTESTED"
        }
        if (
            result.subject_id != state.subject_id
            or result.base_revision != snapshot.revision
        ):
            raise AiSchemaInvalid("Agent Worker changed Subject or baseline revision")
        if len({t.trait_id for t in result.traits}) != len(result.traits):
            raise AiSchemaInvalid("Duplicate trait identifiers")
        for trait in result.traits:
            if not set(trait.evidence_ids + trait.counter_evidence_ids) <= allowed:
                raise AiSchemaInvalid("Trait references unauthorized material")
        return Snapshot(
            subject_id=state.subject_id,
            revision=snapshot.revision + 1,
            traits=result.traits,
            model_version=result.model_version,
            prompt_version=result.prompt_version,
            updated_at=utcnow(),
            limitations=snapshot.limitations,
        )

    def commit_snapshot(self, state, snapshot, materials):
        # Source consent and grant generation join the revision CAS. A revocation
        # landing during a provider call must refuse that call's pending write.
        active_consent = exists(
            select(Consent.consent_id).where(
                Consent.consent_id == AgentState.recording_consent_id,
                Consent.status == "granted",
                Consent.revoked_at.is_(None),
            )
        )
        landed = self.session.execute(
            update(AgentState)
            .where(
                AgentState.state_id == state.state_id,
                AgentState.revision == snapshot.revision - 1,
                AgentState.generation == state.generation,
                AgentState.active.is_(True),
                active_consent,
            )
            .values(
                revision=snapshot.revision, snapshot=snapshot.model_dump(mode="json")
            )
            .execution_options(synchronize_session=False)
        )
        if landed.rowcount != 1:
            raise AgentConflict(
                "Persona changed or consent was revoked; refresh before retrying"
            )
        self.session.add(
            AgentRevision(
                revision_id=f"{state.state_id}:{snapshot.revision}",
                state_id=state.state_id,
                revision=snapshot.revision,
                snapshot=snapshot.model_dump(mode="json"),
                processed_evidence_ids=[m.evidence_id for m in materials],
            )
        )
        self.session.flush()
        self.session.expire(state)

    def refresh(self, state, include_episode_id=None):
        materials = self.materials(state, include_episode_id)
        snapshot = self.snapshot(state, materials)
        new_ids = [
            m.evidence_id
            for m in materials
            if m.evidence_id not in self.processed(state)
            and m.source_type in {"SUBJECT", "CALIBRATION"}
            and m.speaker_authority == "SELF_ATTESTED"
        ]
        if not new_ids:
            return snapshot
        if len(new_ids) > 40:
            raise RequestInvalid(
                "Experimental Agent update budget exceeded (40 new evidence items)"
            )
        result = self.client.persona(
            PersonaInput(
                subject_id=state.subject_id,
                snapshot=snapshot,
                materials=materials,
                new_evidence_ids=new_ids,
            )
        )
        self.guard(state, snapshot.revision)
        if not {m.evidence_id for m in materials} <= {
            m.evidence_id for m in self.materials(state, include_episode_id)
        }:
            raise ConsentInvalid("Source material was withdrawn during processing")
        updated = self.validate_persona(result, state, snapshot, materials)
        self.commit_snapshot(state, updated, materials)
        return updated

    def twin(self, state, question):
        materials = self.materials(state)
        snapshot = self.snapshot(state, materials)
        answer = self.client.twin(
            TwinInput(
                subject_id=state.subject_id,
                question=question,
                snapshot=snapshot,
                materials=materials,
            )
        )
        allowed = {m.evidence_id: m for m in materials}
        if (
            answer.subject_id != state.subject_id
            or answer.revision != snapshot.revision
            or not set(answer.evidence_ids) <= allowed.keys()
        ):
            raise AiSchemaInvalid(
                "Twin changed Subject/revision or referenced unauthorized evidence"
            )
        resolved = [allowed[eid] for eid in answer.evidence_ids]
        if answer.response_type == "ORIGINAL" and (
            len(resolved) != 1 or answer.answer != resolved[0].excerpt
        ):
            raise AiSchemaInvalid("Original is not an exact authorized excerpt")
        if answer.response_type != "INSUFFICIENT" and not resolved:
            raise AiSchemaInvalid("Twin answer lacks evidence")
        answer.evidence = resolved
        # Check persisted authorization again after the external call.
        self.guard(state, answer.revision)
        if not set(answer.evidence_ids) <= {
            m.evidence_id for m in self.materials(state)
        }:
            raise ConsentInvalid("Twin source material was withdrawn during processing")
        return answer

    def reapply_calibration(self, state, calibration_id, expected_revision, *, apply=False):
        """Preview/reproject an existing completed correction after worker fixes.

        Local maintenance only; the immutable lock and original revision remain
        history. Normal authorization, provenance and revision CAS still apply.
        """
        self.guard(state, expected_revision)
        record = self.record(state, calibration_id)
        if record.state != "COMPLETED":
            raise AgentConflict("Only a completed calibration can be reapplied")
        materials = self.materials(state)
        correction = next((m for m in materials if m.source_ref == "calibration:" + calibration_id), None)
        if correction is None:
            raise ConsentInvalid("Calibration material is unavailable")
        if any(m.source_type == "CALIBRATION" and m.context == correction.context
               and m.observed_at > correction.observed_at for m in materials):
            raise AgentConflict("A newer calibration exists; reapply the latest correction")
        snapshot = self.snapshot(state, materials)
        result = self.client.persona(PersonaInput(subject_id=state.subject_id, snapshot=snapshot,
            materials=materials, new_evidence_ids=[correction.evidence_id]))
        self.guard(state, expected_revision)
        if not {m.evidence_id for m in materials} <= {m.evidence_id for m in self.materials(state)}:
            raise ConsentInvalid("Source material was withdrawn during reapplication")
        updated = self.validate_persona(result, state, snapshot, materials)
        if apply:
            self.commit_snapshot(state, updated, materials)
            self.session.commit()
        return updated

    def lock(self, state, question):
        answer = self.twin(state, question)
        locked_at = utcnow()
        record = CalibrationRecord(
            calibration_id="cal_" + uuid4().hex,
            state_id=state.state_id,
            question=question,
            locked_answer=answer.model_dump(mode="json"),
            locked_at=locked_at,
            lock_digest=sha256(
                json.dumps(
                    {
                        "question": question,
                        "answer": answer.model_dump(mode="json"),
                        "locked_at": locked_at.isoformat(),
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode()
            ).hexdigest(),
            state="LOCKED",
        )
        self.session.add(record)
        self.session.commit()
        return self.view(record)

    def record(self, state, calibration_id):
        record = self.session.get(CalibrationRecord, calibration_id)
        if record is None or record.state_id != state.state_id:
            raise AgentNotFound("Calibration not found")
        allowed = {m.evidence_id for m in self.materials(state)}
        if (
            not set(record.locked_answer["evidence_ids"]) <= allowed
            or record.state == "INVALIDATED"
        ):
            raise ConsentInvalid("Calibration source material was withdrawn")
        return record

    @staticmethod
    def view(record):
        return CalibrationView(
            calibration_id=record.calibration_id,
            question=record.question,
            locked_answer=record.locked_answer,
            locked_at=as_utc(record.locked_at),
            lock_digest=record.lock_digest,
            state=record.state,
            comparison=record.comparison,
            resulting_revision=record.resulting_revision,
        )

    def submit(self, state, record, request):
        if record.state == "COMPLETED":
            if record.human_answer != request.human_answer:
                raise AgentConflict("A completed calibration is immutable")
            return self.view(record)
        if state.revision != request.expected_revision:
            raise AgentConflict(
                "Model changed; refresh and explicitly retry this calibration"
            )
        locked = TwinAnswer.model_validate(record.locked_answer)
        comparison = self.client.compare(
            CompareInput(
                subject_id=state.subject_id,
                question=record.question,
                locked_answer=locked,
                human_answer=request.human_answer,
            )
        )
        self.guard(state, request.expected_revision)
        material = Material(
            evidence_id="cev_"
            + sha256(record.calibration_id.encode()).hexdigest()[:32],
            excerpt=request.human_answer,
            source_type="CALIBRATION",
            source_ref="calibration:" + record.calibration_id,
            observed_at=utcnow(),
            context=record.question[:1000],
            speaker_authority="SELF_ATTESTED",
        )
        materials = self.materials(state) + [material]
        if len(materials) > 160:
            raise RequestInvalid("Experimental Agent material budget exceeded (160)")
        snapshot = self.snapshot(state, materials)
        result = self.client.persona(
            PersonaInput(
                subject_id=state.subject_id,
                snapshot=snapshot,
                materials=materials,
                new_evidence_ids=[material.evidence_id],
            )
        )
        self.guard(state, request.expected_revision)
        current_ids = {m.evidence_id for m in self.materials(state)} | {
            material.evidence_id
        }
        if not {m.evidence_id for m in materials} <= current_ids:
            raise ConsentInvalid(
                "Calibration source material was withdrawn during processing"
            )
        updated = self.validate_persona(result, state, snapshot, materials)
        self.commit_snapshot(state, updated, materials)
        self.session.add(
            AgentMaterial(
                evidence_id=material.evidence_id,
                state_id=state.state_id,
                calibration_id=record.calibration_id,
                excerpt=material.excerpt,
                context=material.context,
                observed_at=material.observed_at,
            )
        )
        changed = self.session.execute(
            update(CalibrationRecord)
            .where(
                CalibrationRecord.calibration_id == record.calibration_id,
                CalibrationRecord.state == "LOCKED",
            )
            .values(
                state="COMPLETED",
                human_answer=request.human_answer,
                comparison=comparison.model_dump(mode="json"),
                resulting_revision=updated.revision,
            )
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount != 1:
            raise AgentConflict("Calibration was completed concurrently")
        self.session.commit()
        self.session.refresh(record)
        return self.view(record)

    def withdraw_episode(self, state, episode_id):
        episode = self.session.get(Episode, episode_id)
        if (
            not episode
            or episode.actor_id != state.actor_id
            or episode.subject_id != state.subject_id
        ):
            raise AgentNotFound("Episode not found")
        if episode_id in state.excluded_episode_ids:
            return self.snapshot(state)
        excluded = sorted(set(state.excluded_episode_ids) | {episode_id})
        all_records = list(
            self.session.scalars(
                select(CalibrationRecord).where(
                    CalibrationRecord.state_id == state.state_id
                )
            )
        )
        affected_records = [
            r
            for r in all_records
            if any(
                e.get("episode_id") == episode_id for e in r.locked_answer["evidence"]
            )
        ]
        affected_ids = {r.calibration_id for r in affected_records}
        while True:
            descendants = [
                r
                for r in all_records
                if r.calibration_id not in affected_ids
                and any(
                    e.get("source_ref", "").removeprefix("calibration:") in affected_ids
                    for e in r.locked_answer["evidence"]
                )
            ]
            if not descendants:
                break
            affected_records.extend(descendants)
            affected_ids.update(r.calibration_id for r in descendants)
        materials = [
            m
            for m in self.materials(state)
            if m.episode_id != episode_id
            and not (
                m.source_type == "CALIBRATION"
                and m.source_ref.removeprefix("calibration:") in affected_ids
            )
        ]
        allowed = {m.evidence_id for m in materials}
        old = self.snapshot(state)
        # Conservative dependency invalidation: don't leave a conclusion whose
        # supporting or counter-evidence was removed.
        traits = [
            t
            for t in old.traits
            if set(t.evidence_ids + t.counter_evidence_ids) <= allowed
        ]
        updated = old.model_copy(
            update={
                "traits": traits,
                "revision": old.revision + 1,
                "updated_at": utcnow(),
            }
        )
        self.commit_snapshot(state, updated, materials)
        state.excluded_episode_ids = excluded
        for record in affected_records:
            record.state = "INVALIDATED"
        self.session.commit()
        return updated

    def plan(self, state):
        snapshot = self.snapshot(state)
        conflicted = next(
            (t for t in snapshot.traits if t.status == "CONFLICTED"), None
        )
        if conflicted:
            return Plan(
                subject_id=state.subject_id,
                revision=state.revision,
                question=f"关于“{conflicted.statement[:120]}”，哪些情境适用，哪些不适用？",
                reason="优先澄清已有证据中的矛盾",
                target_domain=conflicted.domain,
                related_trait_ids=[conflicted.trait_id],
            )
        questions = [
            ("VALUES", "最近一次你觉得很重要的选择是什么？为什么？"),
            ("DECISION_PATTERNS", "面对两个都不错的选择时，你通常先考虑什么？"),
            ("RELATIONSHIPS", "最近与你最亲近的人一起做了什么？"),
            ("PREFERENCES", "下班后和周末，你分别喜欢怎么度过？"),
            ("EXPRESSION", "如果安慰一位难过的朋友，你会怎么说？"),
            ("IDENTITY", "你希望别人怎样介绍你？"),
            ("EPISODIC_MEMORY", "最近有什么让你一直记得的小事？"),
        ]
        covered = {t.domain for t in snapshot.traits if t.status != "SUPERSEDED"}
        domain, question = next(
            ((d, q) for d, q in questions if d not in covered), questions[0]
        )
        return Plan(
            subject_id=state.subject_id,
            revision=state.revision,
            question=question,
            reason="按领域缺口的固定优先顺序选择一个问题；启发式，不是已测信息增益",
            target_domain=domain,
        )
