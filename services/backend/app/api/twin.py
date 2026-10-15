"""Subject-scoped evidence search and Twin answers."""

from __future__ import annotations

from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..errors import AppError
from ..models import (Actor, Consent, ConsentScope, Episode, Evidence,
                      ModelRevision, PersonTrait, TwinAnswer, utcnow)
from ..repositories.consents import ConsentRepository
from ..retrieval import EmbeddingUnavailable, retrieve
from ..security import current_actor
from ..twin_client import TwinUnavailable
from ..stt import SttProvider
from ..access import visible_episodes, is_owner, require_cloud, source_basis, publication_lock, altered_story_ids
from ..materials import effective_materials, ContextTooLarge
from ..rag_contract import (AuthorizedSnapshot, AuthorizedSource, ContextGroup,
                            RagContextIncomplete, build_rag_provider, retrieve_context)

router = APIRouter(prefix="/api/v1/subjects/{subject_id}", tags=["twin"])


class TwinNotFound(AppError):
    code = "NOT_FOUND"
    http_status = 404


class TwinFailed(AppError):
    code = "TWIN_UNAVAILABLE"
    http_status = 503


class SourceChanged(AppError):
    code = 'SOURCE_CHANGED'
    http_status = 409


class TwinQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)
    cloud_consent_id: str = Field(min_length=1)
    mode: Literal['evidence','persona'] = 'evidence'
    retrieval_mode: Literal['full','local'] = 'full'


@router.post("/twin/transcribe-query")
async def transcribe_query(subject_id: str, request: Request,
                           actor: Actor = Depends(current_actor),
                           session: Session = Depends(get_session)) -> dict:
    """Temporary speech-to-text; never create an Episode or Memory."""
    require_subject(session, subject_id, actor)
    from ..cloud_asr import CLOUD_BACKENDS
    if request.app.state.settings.stt_backend not in {"http", *CLOUD_BACKENDS}:
        raise TwinFailed("请先连接真实的中文语音识别服务。")
    cloud = request.app.state.settings.stt_backend in CLOUD_BACKENDS
    if cloud:
        from ..cloud_asr import cloud_policy
        from ..errors import RequestInvalid
        if request.headers.get('X-Cloud-ASR-Policy') != cloud_policy(request.app.state.settings):
            raise RequestInvalid('请明确同意将提问原音发送到当前云端转写服务。')
    audio = await request.body()
    if not audio or len(audio) > 8 * 1024 * 1024:
        raise TwinFailed("提问录音为空或过大。")
    provider: SttProvider = request.app.state.stt_provider
    try:
        mime = request.headers.get('Content-Type', 'audio/mp4')
        if cloud:
            def authorize():
                with request.app.state.database.session() as guard:
                    require_subject(guard, subject_id, actor)
            transcript = await run_in_threadpool(provider.transcribe_authorized, audio, mime, authorize)
        else:
            transcript = await run_in_threadpool(provider.transcribe, audio, mime)
    except AppError as exc:
        raise TwinFailed("提问录音暂时无法识别，可直接输入问题。") from exc
    from ..chinese_text import simplified_transcript
    return {"text": simplified_transcript(transcript.text), "stt_model_version": transcript.model_version}


def require_subject(session: Session, subject_id: str, actor: Actor) -> None:
    from ..access import require_owner
    require_owner(session, subject_id, actor.actor_id)
    grant = session.scalar(select(Consent).where(
        Consent.subject_id == subject_id, Consent.granted_by_actor_id == actor.actor_id,
        Consent.scope == str(ConsentScope.RECORDING), Consent.status == "granted",
        Consent.revoked_at.is_(None),
    ))
    if grant is None:
        raise TwinNotFound("Subject not found")


def answer_view(session: Session, row: TwinAnswer) -> dict:
    from ..persona_models import PersonaAnswerContext
    meta=session.get(PersonaAnswerContext,row.answer_id)
    review=meta.review_summary if meta and row.invalidated_at is None else {}
    sources = [session.get(Evidence, identifier) for identifier in row.evidence_ids]
    return {
        "answer_id": row.answer_id, "subject_id": row.subject_id,
        "question": row.question, "answer": row.answer if row.invalidated_at is None else "相关记忆已变化，请重新提问。",
        "response_type": row.response_type, "confidence": row.confidence,
        "model_version": row.model_version, "person_model_version": row.person_model_version,
        "source_version": row.source_basis,
        "created_at": row.created_at.isoformat(),
        "stale": row.invalidated_at is not None,
        "mode": meta.mode if meta else 'evidence',
        "understanding_ids": meta.understanding_ids if meta and row.invalidated_at is None else [],
        "contribution_ids": meta.contribution_ids if meta and row.invalidated_at is None else [],
        "prompt_version": meta.prompt_version if meta else '',
        "coverage": review.get('coverage'),
        "omitted_points": review.get('omitted_points'),
        "expression": row.expression if row.invalidated_at is None else None,
        "evidence": [{"evidence_id": source.evidence_id, "excerpt": source.excerpt,
                      "episode_id": source.episode_id, "source_type": source.source_type}
                     for source in sources if source is not None] if row.invalidated_at is None else [],
    }


@router.get("/memory-search")
def search_memories(subject_id: str, q: str, request: Request,
                    actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    actor_id = actor.actor_id
    publication_lock(session, subject_id)
    ids = visible_episodes(session, subject_id, actor.actor_id)
    basis = source_basis(session, subject_id)
    reader = not is_owner(session, subject_id, actor_id)
    session.commit()
    if not q.strip() or len(q) > 1000:
        return {"items": []}
    try:
        items = retrieve(session, subject_id, q.strip(), request.app.state.embedding_encoder,
                         episode_ids=ids, reader=reader)
        session.commit()
    except EmbeddingUnavailable as exc:
        raise TwinFailed(str(exc)) from exc
    publication_lock(session, subject_id)
    if basis != source_basis(session, subject_id):
        raise SourceChanged('资料或授权已变化，请重新搜索。')
    visible_episodes(session, subject_id, actor_id)
    session.commit()
    return {"items": items}


@router.post("/twin/answers")
def ask(subject_id: str, payload: TwinQuestion, request: Request,
        actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    return generate_answer(subject_id,payload,request,actor,session)


def generate_answer(subject_id, payload, request, actor, session, *, voice_context=None,
                    cancel_check=lambda: None,on_retrieved=lambda: None,material_cache=None,
                    on_source_prepared=None,selection_cache=None,prepare_only=False,context_only=False):
    cancel_check()
    actor_id = actor.actor_id
    from ..narrative import visible_records,contextual_sources
    from ..models import NarrativePreference
    from ..person_context import persona_understandings
    loaded={}
    def load_snapshot():
        cancel_check()
        # Transactions guard snapshots, never the retrieval or model call.
        publication_lock(session,subject_id)
        require_cloud(session,subject_id,actor_id,payload.cloud_consent_id)
        ids=visible_episodes(session,subject_id,actor_id,cloud=True)
        reader=not is_owner(session,subject_id,actor_id)
        if reader: ids-=altered_story_ids(session,ids)
        current_basis=source_basis(session,subject_id)
        cache_key=(subject_id,actor_id,payload.cloud_consent_id,payload.retrieval_mode,
                   current_basis,tuple(sorted(ids)),reader)
        # Request-local, only after fresh authorization and a complete source
        # fingerprint under the publication lock. Never cache across actors or
        # skip the post-retrieval check. This avoids rebuilding the same archive
        # three times while preserving detection of writes during retrieval.
        previous=loaded.get('snapshot')
        if (previous is not None and previous.source_basis==current_basis
                and loaded['ids']==ids and loaded['reader']==reader):
            session.commit()
            return previous
        cached=material_cache.get(cache_key) if material_cache is not None else None
        if cached is not None:
            loaded.clear();loaded.update(cached)
            session.commit()
            return loaded['snapshot']
        candidates=effective_materials(session,subject_id,ids,enforce_budget=payload.retrieval_mode=='full')
        sources=contextual_sources(session,subject_id,candidates,visible_episode_ids=ids)
        organized=[r for r in visible_records(session,subject_id,actor_id,sources=sources)
                   if r['status']=='confirmed' and r['source_valid']]
        understandings=persona_understandings(session,subject_id,actor_id,sources)
        groups=[ContextGroup('story',tuple(r['evidence_ids'])) for r in organized
                if r['kind'] in {'story','person','observation'} and r['evidence_ids']]
        groups.extend(ContextGroup('understanding',tuple(dict.fromkeys(u['evidence_ids']+u['counter_evidence_ids'])))
                      for u in understandings if u['evidence_ids'])
        if payload.retrieval_mode=='local':
            from ..models import MemoryRevision, MemoryItem
            from collections import defaultdict
            by_episode=defaultdict(set)
            for source in sources.values(): by_episode[source['episode_id']].add(source['evidence_id'])
            for update in session.scalars(select(MemoryRevision).where(
                    MemoryRevision.subject_id==subject_id,MemoryRevision.status=='confirmed')):
                old_memory=session.get(MemoryItem,update.target_memory_id)
                old=by_episode.get(old_memory.episode_id,set()) if old_memory else set()
                new=by_episode.get(update.episode_id,set())
                if old and not new and update.kind in {'change','supplement'}:
                    raise RagContextIncomplete('相关补充目前不可用，请先核对分享范围或处理状态。')
                if old and new:
                    groups.append(ContextGroup('correction',tuple(sorted(old|new))))
        wrapped=[]
        for source in sources.values():
            episode=session.get(Episode,source['episode_id'])
            if episode is None or episode.subject_id!=subject_id:
                raise SourceChanged('资料归属已变化，请重新提问。')
            wrapped.append(AuthorizedSource(episode.subject_id,source))
        # effective_materials can register previously unextracted exact spans.
        # Their persisted IDs are part of the snapshot, so fingerprint after it.
        snapshot=AuthorizedSnapshot(subject_id,source_basis(session,subject_id),tuple(wrapped),tuple(groups))
        loaded.update(ids=ids,reader=reader,candidates=candidates,sources=sources,
                      organized=organized,understandings=understandings,snapshot=snapshot)
        if material_cache is not None:
            material_cache.put((subject_id,actor_id,payload.cloud_consent_id,payload.retrieval_mode,
                snapshot.source_basis,tuple(sorted(ids)),reader),loaded)
        session.commit()
        return snapshot
    snapshot=load_snapshot()
    retrieval_audit={'mode':'full'}
    if payload.retrieval_mode=='local':
        provider=build_rag_provider(session,request.app.state.embedding_encoder,
            episode_ids=loaded['ids'],reader=loaded['reader'],sources=loaded['sources'])
        retrieval_question=payload.question
        if voice_context:
            # Only lookup hints. The model receives history separately as non-evidence.
            previous=voice_context[-1]['question']
            if len(previous)+len(retrieval_question)<980:
                retrieval_question=previous+'；追问：'+retrieval_question
        selection_key=(subject_id,actor_id,payload.cloud_consent_id,payload.mode,snapshot.signature)
        selection=selection_cache.get(selection_key,retrieval_question) if selection_cache is not None else None
        prefetched=selection is not None
        if selection is None:
            selection=retrieve_context(retrieval_question,load_snapshot,provider)
            cancel_check()
            if selection_cache is not None:selection_cache.put(selection_key,retrieval_question,selection)
        retrieval_audit={'mode':'local','source_basis':selection.source_basis,
            'retriever_version':selection.retriever_version,'hit_ids':list(selection.hit_ids),
            'selected_evidence_ids':list(selection.selected_evidence_ids),
            'expanded_ids':list(selection.expanded_ids),'character_count':selection.character_count,
            'prefetched_selection':prefetched}
        selected=set(selection.selected_evidence_ids)
        candidates=[dict(c,evidence=[e for e in c['evidence'] if e['evidence_id'] in selected])
                    for c in loaded['candidates'] if any(e['evidence_id'] in selected for e in c['evidence'])]
        sources=dict(selection.sources)
        snapshot_basis=selection.source_basis
    else:
        candidates=loaded['candidates'];sources=loaded['sources'];snapshot_basis=snapshot.source_basis
    organized=loaded['organized']
    understandings=[u for u in loaded['understandings']
                    if set(u['evidence_ids']+u['counter_evidence_ids'])<=sources.keys()]
    publication_lock(session,subject_id)
    if snapshot_basis!=source_basis(session,subject_id):
        raise SourceChanged('资料或授权已变化，请重新提问。')
    require_cloud(session,subject_id,actor_id,payload.cloud_consent_id)
    for trait in understandings:
        # Conditions and counterexamples need the same permission check as support.
        if not set(trait['evidence_ids']+trait['counter_evidence_ids'])<=sources.keys(): continue
        for candidate in candidates:
            if set(trait['evidence_ids']).intersection(e['evidence_id'] for e in candidate['evidence']):
                counters='；'.join(sources[e]['excerpt'] for e in trait['counter_evidence_ids'])
                candidate['traits'].append(f"本人确认的理解：{trait['statement']}；情境：{trait['context']}；例外：{counters}；仅适用于所述情境。")
    for record in organized:
        if record['kind'] not in {'story','person','observation'}: continue
        for candidate in candidates:
            if set(record['evidence_ids']).intersection(e['evidence_id'] for e in candidate['evidence']):
                candidate['traits'].append('本人审核的故事整理（非原话，以证据为准）：'+record['text'])
    pref=session.get(NarrativePreference,subject_id)
    examples=[{'id':r['id'],'text':r['text']} for r in organized if r['kind']=='style'] if pref and pref.style_enabled else []
    from ..errors import RequestInvalid
    if payload.mode=='persona' and (not pref or not pref.style_enabled or not examples or not loaded['understandings']):
        raise RequestInvalid('请先由本人开启分身表达，并确认可使用的人物理解和表达范例。')
    from ..persona_context import visible_contributions, select_contributions
    contributions=visible_contributions(session,subject_id,actor_id,
        enforce_budget=payload.retrieval_mode=='full',
        selection_metadata=payload.retrieval_mode=='local') if payload.mode=='persona' else []
    if payload.retrieval_mode=='local':
        contributions=select_contributions(contributions,retrieval_question)
        contributions=[{k:v for k,v in note.items() if k not in {'narrative_ids','status'}} for note in contributions]
    style_over_budget=len(examples)>8 or sum(len(r['text']) for r in examples)>4000
    if sum(map(len,{t for c in candidates for t in c['traits']})) > 24000:
        raise ContextTooLarge('已确认的人物理解超过上下文预算，请拒绝已不适用的候选；没有截断。')
    from ..twin_context import contextual_evidence
    twin_sources = contextual_evidence(session, sources)
    basis = source_basis(session, subject_id)
    revision = session.get(ModelRevision, subject_id)
    basis_version = revision.version if revision else 0
    session.commit()
    question = payload.question.strip()
    if not question:
        raise TwinNotFound("Question is empty")
    candidate_ids = {row["memory_item_id"] for row in candidates}
    unresolved = set()
    # Explicit temporal revisions travel as context; an unrelated contradiction
    # must not globally block answering facts from the same recording.
    limited = [{"memory_item_id": row["memory_item_id"], "statement": row["statement"],
                "domain": row["domain"], "unresolved": row["memory_item_id"] in unresolved,
                "traits": row["traits"], "graph_facts": row["graph_facts"],
                "evidence": [twin_sources[source["evidence_id"]]
                             for source in row["evidence"] if source["excerpt"]]}
               for row in candidates]
    # Retrieval may update cached vectors. Release its transaction before the
    # network call so revocation can proceed while DeepSeek is working.
    session.commit()
    on_retrieved()
    cancel_check()
    publication_lock(session, subject_id)
    if basis != source_basis(session, subject_id):
        raise SourceChanged('资料或授权已变化，请重新提问。')
    require_cloud(session,subject_id,actor_id,payload.cloud_consent_id)
    session.commit()
    if prepare_only:return {'prepared':True,'retrieval':retrieval_audit}
    if context_only:
        # Internal voice adapter only. The public question schema cannot request
        # this payload. All retrieval, revision and permission checks above apply.
        if payload.mode=='persona' and style_over_budget:
            raise ContextTooLarge('表达范例超出本轮范围，请缩小问题范围。')
        return dict(question=question,mode=payload.mode,candidates=limited,
            understandings=understandings if payload.mode=='persona' else [],
            examples=examples if payload.mode=='persona' else [],contributions=contributions,
            dialogue_context=voice_context or [],source_version=basis,
            evidence=list(twin_sources.values()),retrieval=retrieval_audit)
    if not limited and not contributions:
        result = {"answer": "现有记录还不足以确定。", "response_type": "UNKNOWN",
                  "evidence_ids": [], "confidence": 0, "model_version": "no-evidence"}
    else:
        if request.app.state.settings.ai_backend != "http":
            raise TwinFailed("请先连接真实的 AI Core 服务。")
        if on_source_prepared is not None and payload.mode=='evidence':
            # One private authorized retrieval-hit synthesis can overlap LLM
            # selection. It never chooses or publishes an answer.
            hit=next((twin_sources[i] for i in retrieval_audit.get('hit_ids',[])
                      if i in twin_sources and twin_sources[i]['source_type']=='SUBJECT'),None)
            if hit is not None and len(hit['excerpt'])<=500:on_source_prepared(hit['excerpt'])
        try:
            if payload.mode=='persona':
                model_input=dict(question=question,candidates=limited,
                    understandings=understandings,examples=examples,contributions=contributions)
                if voice_context is not None:
                    model_input.update(dialogue_context=voice_context,voice_response=True)
                result=request.app.state.twin_client.persona(model_input)
            else:
                result = request.app.state.twin_client.answer(question, limited)
        except TwinUnavailable as exc:
            failure = TwinFailed(str(exc))
            if not exc.retryable:
                failure.code = exc.code
                failure.http_status = 502
            raise failure from exc
    cancel_check()
    expression=None
    if payload.mode=='persona':
        pass
    elif voice_context is not None:
        pass  # Voice answers already have their reviewed wording; no extra style pass.
    elif examples and result.get('response_type')=='SIMULATION' and style_over_budget:
        expression={'status':'unavailable','text':'','model_version':'','prompt_version':'expression-checked-v1',
                    'reason':'表达范例超过8条或4000字，本次仅提供有来源的回答。'}
    elif examples and result.get('response_type')=='SIMULATION':
        publication_lock(session,subject_id)
        if basis!=source_basis(session,subject_id):
            raise SourceChanged('资料或授权已变化，请重新提问。')
        require_cloud(session,subject_id,actor_id,payload.cloud_consent_id)
        session.commit()
        # Only this optional pass may degrade; never replace a failed fact answer.
        expression=request.app.state.twin_client.express(result['answer'],examples)
    publication_lock(session, subject_id)
    if basis != source_basis(session, subject_id):
        raise SourceChanged('资料或授权已变化，请重新提问。')
    require_cloud(session, subject_id, actor_id, payload.cloud_consent_id)
    valid = {source["evidence_id"]: (source, row) for row in candidates for source in row["evidence"]}
    kind = result.get("response_type")
    used_traits=result.get('understanding_ids',[]) if payload.mode=='persona' else []
    used_notes=result.get('contribution_ids',[]) if payload.mode=='persona' else []
    if payload.mode=='persona':
        def ids_valid(ids,rows):
            return isinstance(ids,list) and all(isinstance(i,str) for i in ids) and len(ids)==len(set(ids)) and set(ids)<={r['id'] for r in rows}
        if kind=='ORIGINAL' or not ids_valid(used_traits,understandings) or not ids_valid(used_notes,contributions):
            raise TwinFailed('分身回答的依据不完整。')
        required={e for u in understandings if u['id'] in used_traits for e in u['evidence_ids']+u['counter_evidence_ids']}
        if not required<=set(result.get('evidence_ids',[])): raise TwinFailed('分身回答遗漏了理解的依据或例外。')
    cited = result.get("evidence_ids")
    content = result.get("answer")
    confidence = result.get("confidence")
    version = result.get("model_version")
    review_summary={}
    if payload.mode=='persona' and ('coverage' in result or 'omitted_points' in result):
        coverage=result.get('coverage'); omitted=result.get('omitted_points')
        if (coverage not in {'complete','partial'} or type(omitted) is not int
                or not 0<=omitted<=4 or (coverage=='complete' and omitted!=0)
                or (kind=='UNKNOWN' and omitted!=0)):
            raise TwinFailed('回答覆盖状态不完整，本次未保存答案。')
        review_summary={'coverage':coverage,'omitted_points':omitted}
    if payload.mode=='persona' and kind=='UNKNOWN' and (cited or used_traits or used_notes):
        raise TwinFailed('未知回答不能携带已被删除的事实或人物依据。')
    review_summary['retrieval']=retrieval_audit
    if 'semantic_review' in result:
        if result['semantic_review'] not in {'performed','skipped'}:
            raise TwinFailed('回答核对状态无效。')
        review_summary['semantic_review']=result['semantic_review']
    if (kind not in {"ORIGINAL", "SIMULATION", "UNKNOWN"} or not isinstance(cited, list)
            or not isinstance(content, str) or len(content) > 500
            or not isinstance(confidence, (float, int)) or not 0 <= confidence <= 1
            or not isinstance(version, str) or not version or len(version) > 128
            or len(cited) != len(set(cited)) or any(identifier not in valid for identifier in cited)):
        raise TwinFailed("模型回答的证据格式不正确。")
    if kind == "UNKNOWN":
        content, cited, confidence = "现有记录还不足以确定。", [], 0
    elif (not cited and not used_notes) or not content.strip():
        raise TwinFailed("模型回答缺少可核对的证据。")
    if kind == "ORIGINAL":
        def verified_original(identifier: str) -> bool:
            source = session.get(Evidence, identifier)
            if (source is None or source.source_type != "SUBJECT" or
                    source.span_start is None or source.span_end is None):
                return False
            episode = session.get(Episode, source.episode_id)
            if episode is None or episode.subject_id != subject_id or not episode.transcript:
                return False
            return (episode.transcript[source.span_start:source.span_end] == source.excerpt
                    and content.strip("“”\"'。 ") == source.excerpt.strip("“”\"'。 "))

        if not any(verified_original(identifier) for identifier in cited):
            raise TwinFailed("模型给出的原话无法在录音转写中定位。")
    if kind == "SIMULATION" and any(valid[identifier][1]["memory_item_id"] in unresolved for identifier in cited):
        kind, content, cited, confidence = "UNKNOWN", "现有记录有不同说法，还不能确定。", [], 0
    row = TwinAnswer(answer_id="ta_" + uuid4().hex[:16], subject_id=subject_id,
                     actor_id=actor.actor_id, question=question, answer=content,
                     response_type=kind, evidence_ids=cited,
                     memory_item_ids=list({valid[identifier][1]["memory_item_id"] for identifier in cited}),
                     confidence=confidence, model_version=version,
                     person_model_version=basis_version,
                     source_basis=basis,
                     expression=expression,
                     created_at=utcnow())
    session.add(row)
    session.flush()
    from ..persona_models import PersonaAnswerContext
    session.add(PersonaAnswerContext(answer_id=row.answer_id,mode=payload.mode,
        cloud_consent_id=payload.cloud_consent_id,understanding_ids=used_traits,contribution_ids=used_notes,
        prompt_version=result.get('prompt_version','') if payload.mode=='persona' else '',
        review_summary=review_summary))
    cancel_check()
    session.commit()
    return answer_view(session, row)


@router.get("/twin/answers/{answer_id}")
def read_answer(subject_id: str, answer_id: str,
                actor: Actor = Depends(current_actor), session: Session = Depends(get_session)) -> dict:
    actor_id=actor.actor_id
    publication_lock(session,subject_id)
    visible_episodes(session, subject_id, actor_id)
    row = session.scalar(select(TwinAnswer).where(
        TwinAnswer.answer_id == answer_id, TwinAnswer.subject_id == subject_id,
        TwinAnswer.actor_id == actor.actor_id))
    if row is None:
        raise TwinNotFound("Answer not found")
    from ..twin_validity import require_answer_disclosed
    require_answer_disclosed(session,answer_id)
    if row.invalidated_at is None and row.source_basis != source_basis(session,subject_id):
        row.invalidated_at=utcnow()
        session.commit()
    return answer_view(session, row)
