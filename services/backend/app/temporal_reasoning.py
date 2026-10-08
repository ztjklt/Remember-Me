"""Replayed, subject-scoped temporal/causal graph with auditable path reasoning.

Reported causes describe the subject's attribution, never an identified causal
effect. Ordering/association/hypotheses cannot become causal edges. All nodes,
assertions and paths disappear when their quoted evidence is corrected/deleted.
"""
from collections import deque
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import calendar
import re

from sqlalchemy import select
from .models import Episode, Evidence, MemoryItem, as_utc

VERSION = "temporal-causal-v1"
RELATIONS = {"REPORTED_CAUSE", "DENIES_CAUSE", "BEFORE", "ASSOCIATED_WITH", "HYPOTHESIS"}


def own_rows(session, subject_id):
    rows = session.execute(select(MemoryItem, Episode).join(Episode).where(
        Episode.subject_id == subject_id, MemoryItem.deleted_at.is_(None))).all()
    ids = {eid for m, _ in rows for eid in m.evidence_ids}
    evidence = {e.evidence_id: e for e in session.scalars(select(Evidence).where(Evidence.evidence_id.in_(ids)))}
    result = {}
    for m, ep in rows:
        sources = [evidence.get(eid) for eid in m.evidence_ids]
        if (m.source_type in {"SUBJECT", "CALIBRATION", "AI_INFERENCE"} and sources
                and all(e and e.episode_id == ep.episode_id and e.source_type in {"SUBJECT", "CALIBRATION"} for e in sources)):
            result[m.memory_item_id] = (m, ep, sources)
    return result


def snapshot(session, subject_id, limit=32, query=""):
    rows = sorted(own_rows(session, subject_id).values(), key=lambda row: as_utc(row[1].created_at), reverse=True)
    if query and len(rows) > limit:
        # Old events can outrank recent unrelated records without sending an
        # unbounded lifetime transcript to the provider. Reserve recent context.
        symbols = {ch for ch in query if ch.isalnum()}
        relevant = sorted(rows, key=lambda row: -len(symbols & set(row[0].content)))
        chosen = relevant[:max(1, limit - 8)] + rows[:8]
        rows = list({row[0].memory_item_id: row for row in chosen}.values())
    return [{"memory_item_id": m.memory_item_id, "content": m.content,
             "evidence": [{"evidence_id": e.evidence_id, "excerpt": e.excerpt,
                           "source_type": e.source_type} for e in sources]}
            for m, _, sources in rows[:limit]]


def interval(text):
    """Explicit calendar dates only. Unknown/relative time stays unknown."""
    if not text:
        return None
    match = re.fullmatch(r"(\d{4})(?:年|-)(\d{1,2})(?:(?:月|-)(\d{1,2})日?|月)?", text.strip())
    if not match:
        year = re.fullmatch(r"(\d{4})年", text.strip())
        if not year:
            return None
        y = int(year[1])
        try:
            return {"start": datetime(y, 1, 1, tzinfo=timezone.utc).isoformat(),
                    "end": datetime(y + 1, 1, 1, tzinfo=timezone.utc).isoformat(), "precision": "year"}
        except ValueError:
            return None
    y, month, day = int(match[1]), int(match[2]), int(match[3]) if match[3] else None
    try:
        start = datetime(y, month, day or 1, tzinfo=timezone.utc)
        end = start + timedelta(days=1 if day else calendar.monthrange(y, month)[1])
        return {"start": start.isoformat(), "end": end.isoformat(), "precision": "day" if day else "month"}
    except ValueError:
        return None


def time_relation(left, right):
    """Half-open uncertainty intervals; recording date is never substituted."""
    if not left or not right:
        return "UNKNOWN"
    if left["end"] <= right["start"]:
        return "BEFORE"
    if right["end"] <= left["start"]:
        return "AFTER"
    return "SAME_INTERVAL" if left["start"] == right["start"] and left["end"] == right["end"] else "OVERLAPS"


def event_key(text):
    """Only lossless calendar/first-person framing normalization, no synonyms."""
    text = re.sub(r"^\s*\d{4}(?:年\d{1,2}月(?:\d{1,2}日)?|[-]\d{1,2}(?:[-]\d{1,2})?)", "", text)
    text = re.sub(r"^\s*我", "", text)
    return "".join(ch for ch in text if not ch.isspace() and ch not in "。.!！")


def graph(session, subject_id, *, as_of=None):
    live = own_rows(session, subject_id)
    nodes, edges = {}, {}

    def grounded(mid, content, refs, quote):
        row = live.get(mid)
        if not row or row[0].content != content or not refs or not quote or not quote.strip():
            return False
        sources = {e.evidence_id: e for e in row[2]}
        return (set(refs) <= sources.keys()
                and (not as_of or as_utc(row[1].created_at) <= as_utc(as_of)
                     and all(as_utc(sources[e].created_at) <= as_utc(as_of) for e in refs))
                and any(quote in (sources[e].excerpt or "") for e in refs))

    def node(anchor):
        mid, quote = anchor["memory_item_id"], anchor["quote"]
        if not grounded(mid, anchor["content"], anchor["evidence_ids"], quote):
            return None
        time_text = anchor.get("time_text")
        if time_text and not any(time_text in (e.excerpt or "") for e in live[mid][2] if e.evidence_id in anchor["evidence_ids"]):
            return None
        # A canonical event Memory can be quoted with/without its date or "我".
        # Merge only when both normalize exactly to that EVENT's statement;
        # two different clauses inside a multi-event source remain separate.
        identity = quote
        if live[mid][0].memory_type == "EVENT" and event_key(quote) == event_key(anchor["content"]):
            identity = event_key(quote)
        key = "node_" + sha256((mid + "\0" + identity).encode()).hexdigest()[:20]
        event_time = interval(time_text)
        if as_of and event_time and datetime.fromisoformat(event_time["start"]) > as_utc(as_of):
            return None
        value = {"id": key, "memory_item_id": mid, "quote": quote, "evidence_ids": anchor["evidence_ids"],
                 "event_time": event_time, "time_text": time_text, "recorded_at": as_utc(live[mid][1].recorded_at).isoformat()}
        # Do not let two inconsistent time proposals silently overwrite a node.
        if key in nodes:
            existing = nodes[key]
            if existing["event_time"] and event_time and existing["event_time"] != event_time:
                existing["event_time"] = None
                existing["time_conflict"] = True
            elif event_time and not existing.get("time_conflict"):
                existing["event_time"] = event_time
                existing["time_text"] = time_text
            existing["evidence_ids"] = sorted(set(existing["evidence_ids"] + anchor["evidence_ids"]))
        else:
            nodes.setdefault(key, value)
        return key

    for m, ep, _ in live.values():
        if as_of and as_utc(ep.created_at) > as_utc(as_of):
            continue  # Knowledge cutoff over surviving sources, separate from event dates.
        for item in (m.item_metadata or {}).get("temporal_causal", []):
            try:
                if (item.get("version") != VERSION or item.get("input_statement") != m.content
                        or item.get("relation") not in RELATIONS
                        or not grounded(m.memory_item_id, m.content, item["evidence_ids"], item["quote"])):
                    continue
                context = item.get("context")
                if context and context not in item["quote"]:
                    continue
                a, b = node(item["cause"]), node(item["effect"])
                if not a or not b or a == b:
                    continue
                relation = item["relation"]
                if relation == "REPORTED_CAUSE":
                    if any(w in item["quote"] for w in ("不是因为", "并非因为", "没有导致", "不是原因")):
                        relation = "DENIES_CAUSE"
                    elif any(w in item["quote"] for w in ("可能", "也许", "或许", "不确定", "猜测")):
                        relation = "HYPOTHESIS"
                    elif not any(w in item["quote"] for w in ("因为", "导致", "所以", "使我", "让我", "原因")):
                        continue
                key = (a, b, relation, context)
                edge = edges.setdefault(key, {"cause": a, "effect": b, "relation": relation, "context": context,
                    "assertions": [], "status": "supported", "issues": []})
                edge["assertions"].append({"memory_item_id": m.memory_item_id, "quote": item["quote"],
                    "evidence_ids": item["evidence_ids"], "episode_id": ep.episode_id,
                    "model_version": item["model_version"]})
            except (KeyError, TypeError, AttributeError):
                continue  # Malformed auxiliary metadata must not break capture.
    edges = list(edges.values())
    for edge in edges:
        a, b = nodes[edge["cause"]], nodes[edge["effect"]]
        edge["independent_episodes"] = len({r["episode_id"] for r in edge["assertions"]})
        edge["evidence_ids"] = sorted(set(a["evidence_ids"] + b["evidence_ids"] +
                                        [eid for r in edge["assertions"] for eid in r["evidence_ids"]]))
        edge["support_weight"] = min(.8, .45 + .1 * (edge["independent_episodes"] - 1))
        edge["temporal_relation"] = time_relation(a["event_time"], b["event_time"])
        if a.get("time_conflict") or b.get("time_conflict"):
            edge["issues"].append("time_conflict")
        if edge["relation"] in {"REPORTED_CAUSE", "BEFORE"} and a["event_time"] and b["event_time"]:
            if edge["temporal_relation"] == "AFTER":
                edge["issues"].append("reversed_time")
        if edge["relation"] == "REPORTED_CAUSE" and any(other["relation"] == "DENIES_CAUSE"
                and other["cause"] == edge["cause"] and other["effect"] == edge["effect"]
                and other["context"] == edge["context"] for other in edges):
            edge["issues"].append("counter_evidence")
    ordered = [e for e in edges if e["relation"] in {"REPORTED_CAUSE", "BEFORE"} and not e["issues"]]
    for edge in ordered:
        todo, seen = [edge["effect"]], set()
        while todo:
            n = todo.pop()
            if n == edge["cause"]:
                edge["issues"].append("cycle")
                break
            if n in seen:
                continue
            seen.add(n)
            todo.extend(e["effect"] for e in ordered if e["cause"] == n and e["context"] == edge["context"])
    for edge in edges:
        if edge["issues"]:
            edge["status"] = "contested"
        elif edge["relation"] == "HYPOTHESIS":
            edge["status"] = "unverified"
    return {"version": VERSION, "subject_id": subject_id, "nodes": nodes, "edges": edges}


def paths(model, targets, max_depth=4, limit=32):
    """Bounded ancestry, same-context reported chains; no counterfactual effect."""
    causal = [e for e in model["edges"] if e["relation"] == "REPORTED_CAUSE" and e["status"] == "supported"]
    result = []
    for target in sorted(targets):
        queue = deque([(target, [], {target}, None)])
        while queue and len(result) < limit:
            node, chain, seen, context = queue.popleft()
            if len(chain) >= max_depth:
                continue
            for edge in causal:
                if edge["effect"] != node or edge["cause"] in seen or chain and edge["context"] != context:
                    continue
                route = [edge] + chain
                refs = sorted({eid for e in route for eid in e["evidence_ids"]})
                result.append({"nodes": [route[0]["cause"]] + [e["effect"] for e in route],
                    "evidence_ids": refs, "context": edge["context"], "edges": route,
                    "kind": "REPORTED_CHAIN" if len(route) == 1 else "INFERRED_REPORTED_CHAIN",
                    "weakest_support": min(e["support_weight"] for e in route)})
                queue.append((edge["cause"], route, seen | {edge["cause"]}, edge["context"]))
    return result


def clarification_questions(model):
    seen = set()
    for edge in model["edges"]:
        if edge["status"] not in {"contested", "unverified"}:
            continue
        key = (edge["cause"], edge["effect"], edge["context"])
        if key in seen:
            continue
        seen.add(key)
        a, b = model["nodes"][edge["cause"]]["quote"], model["nodes"][edge["effect"]]["quote"]
        yield f"关于「{a}」和「{b}」，你认为有原因关系，还是只是先后或同时发生？有没有其他解释？", edge["evidence_ids"]


def is_causal_question(question):
    return is_counterfactual(question) or any(w in question for w in ("为什么", "为何", "原因", "导致", "因果", "影响"))


def is_counterfactual(question):
    return (any(w in question for w in ("如果", "假如", "要是", "倘若"))
            and any(w in question for w in ("没", "不", "未"))) or "否则会" in question


def presentation(model, memory_id):
    return [{"relation": edge["relation"], "status": edge["status"], "issues": edge["issues"],
             "cause": model["nodes"][edge["cause"]], "effect": model["nodes"][edge["effect"]],
             "evidence_ids": edge["evidence_ids"], "context": edge["context"],
             "temporal_relation": edge["temporal_relation"],
             "independent_episodes": edge["independent_episodes"],
             "quotes": [a["quote"] for a in edge["assertions"]]}
            for edge in model["edges"] if any(a["memory_item_id"] == memory_id for a in edge["assertions"])]


def augment(session, subject_id, question, candidates):
    if not is_causal_question(question):
        return candidates, []
    model = graph(session, subject_id)
    mids = {c["memory_item_id"] for c in candidates[:5]}
    targets = {n["id"] for n in model["nodes"].values() if n["memory_item_id"] in mids}
    routes = paths(model, targets)
    rows = own_rows(session, subject_id)
    result = list(candidates[:5])
    valid_routes = []
    for route in sorted(routes, key=lambda r: (-len(r["edges"]), r["nodes"])):
        # Every antecedent and assertion must fit the existing eight-candidate,
        # eight-citation envelope. Never truncate a chain into fake evidence.
        ids = {model["nodes"][n]["memory_item_id"] for n in route["nodes"]}
        ids.update(a["memory_item_id"] for e in route["edges"] for a in e["assertions"])
        missing = ids - {c["memory_item_id"] for c in result}
        if len(result) + len(missing) > 8 or len(route["evidence_ids"]) > 8:
            continue
        for mid in sorted(missing):
            m, ep, sources = rows[mid]
            result.append({"memory_item_id": mid, "episode_id": ep.episode_id, "statement": m.content,
                "domain": (m.item_metadata or {}).get("domain"), "traits": [], "graph_facts": [],
                "evidence": [{"evidence_id": e.evidence_id, "excerpt": e.excerpt, "source_type": e.source_type}
                             for e in sources if e.excerpt]})
        valid_routes.append(route)
        labels = " → ".join(model["nodes"][n]["quote"] for n in route["nodes"])
        note = (f"本人归因链（{route['kind']}；不是客观因果证明）：{labels}；"
                f"语境：{route['context'] or '未明示'}；依据：{','.join(route['evidence_ids'])}。"
                "多跳仅为归因链推演，不证明移除原因会改变结果；不得据此回答反事实。")
        for item in result:
            if item["memory_item_id"] in ids and len(item["graph_facts"]) < 8:
                item["graph_facts"] = item["graph_facts"] + [note]
    return result, valid_routes
