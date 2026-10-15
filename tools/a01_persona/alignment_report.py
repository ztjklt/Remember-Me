"""Summarize frozen local runs without changing their first-attempt records."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAR = ROOT / "services/backend/var/a01-20261012"
OUT = VAR / "twin-alignment-review-20261012"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# These are an assistant's source/text review, not a second independent model
# vote, human voice approval, or a real subject's endorsement.
ASSESSMENTS = {
    "v6": {
        "L01": ("supported", "complete", "met_with_repetition", "署名和完整引文有据；第二句重复作者边界。"),
        "L02": ("not_delivered", "not_delivered", "blocked", "审核只看裸草稿，误判程序已显示的署名；本人新立场仍不能由亲友观察直接推出。"),
        "L03": ("supported", "complete", "met", "保留焦味、孩子与现在的条件，先断电再请电工，未改写全部过去维修。"),
        "L04": ("not_delivered", "not_delivered", "blocked", "本机检索依赖缺失，503；不是模型不知道。"),
        "L05": ("not_delivered", "not_delivered", "blocked", "正文使用的姓名没有落在该要点实际选中的片段中；完整ASR有相关姓名，仍须连好指代依据。"),
        "L06": ("supported_unknown", "complete", "met", "未留下的国家和机票日期保留未知，没有制造未来决定。"),
        "L07": ("supported", "complete", "met", "回答已知认识年份；下个月见面的新决定明确未知。"),
        "L08": ("irrelevant_public_quote", "partial", "failed", "未知之后拼了公开桂芳原话，不能回答未分享目标。未发现该答泄漏实际私密原文，仍不合格。"),
    },
    "v7": {
        "L01": ("not_delivered", "not_delivered", "blocked", "作者完整名字已在程序前缀，却被机械规则要求再次出现在引文正文；v8修复这个特定例外。"),
        "L02": ("supported_retained_points", "partial", "partial", "保留亲友原文和未知，剔除无据第一人称新态度；不得记为整题合格。"),
        "L03": ("supported", "complete", "met", "普通小毛病与焦味分开，保留安全边界；一次45秒传输超时后有界重试。"),
        "L04": ("supported", "complete", "met_with_repetition", "真实本地BGE检索后生成有据回答，孩子相关动作重复；冷启动请求112.109秒。"),
        "L05": ("not_delivered", "not_delivered", "blocked", "首稿name_source_mismatch，修正稿name_text_mismatch；不能放宽同名人物规则来算通过。"),
        "L08": ("supported_unknown", "complete", "met", "目标不可见时只返回未知，没有再拼相似公开原话。"),
    },
    "v8": {
        "C01": ("supported", "complete", "met_with_repetition", "完整作者前缀与原文获放行，但同一整段重复两次，呈现仍需优化。此条为既有实际ASR的署名文字副本，不是新录音或新ASR。"),
        "P01": ("supported", "complete", "met", "当前本地RAG真实命中2项并补齐3项，条件化回应有依据；新回答合成为22.08秒音频，未做人工听读。"),
    },
}
FOLDERS = {
    "v6": "twin-alignment-live-20261012",
    "v7": "twin-alignment-v7-targeted-20261012",
    "v8": "twin-alignment-v8-final-20261012",
}


def main():
    cases = []
    for version, folder in FOLDERS.items():
        path = VAR / folder / "run.json"
        data = read(path)
        plan = read(path.with_name("plan.json"))
        for item in plan["cases"]:
            key = item["id"]
            op = data["operations"][key if version == "v8" else "question." + key]
            response = op["response"]
            body = response.get("body", {})
            fact, coverage, outcome, note = ASSESSMENTS[version][key]
            cases.append({"batch": version, "case_id": key, "question": item["question"],
                "request_mode": item.get("retrieval_mode", "full"),
                "http_status": response["http_status"], "elapsed_seconds": op["elapsed_seconds"],
                "answer": body.get("answer"), "answer_id": body.get("answer_id"),
                "service_coverage": body.get("coverage"), "omitted_points": body.get("omitted_points"),
                "error_code": body.get("error_code"), "source_support_review": fact,
                "question_coverage_review": coverage, "assistant_outcome": outcome, "review_note": note,
                "run_path": str(path.relative_to(ROOT)), "run_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write(OUT / "case-review.json", {"reviewer": "assistant_source_text_review",
        "human_listening": "not_performed", "real_person_endorsement": False,
        "warning": "Versions differ and targeted reruns are not a held-out accuracy benchmark. Never select best runs or overwrite historical results.",
        "cases": cases})

    events = []
    log = VAR / "runtime/ai.log"
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    requests = [e for e in events if e.get("event") == "persona_request" and
        e.get("prompt_version") in {"persona-conditional-reviewed-" + v for v in FOLDERS}]
    # Request order is tied to the frozen sequential plans. v6 L04 failed before
    # any model call; it has no invented provider/usage record.
    ordered = [c for c in cases if not (c["batch"] == "v6" and c["case_id"] == "L04")]
    assert len(requests) == len(ordered) == 15
    allowed = {"event", "trace_id", "requested_model", "response_model", "endpoint", "status",
        "prompt_sha256", "json_object_parsed", "timeout_seconds", "usage", "finish_reason",
        "duration_ms", "error_type"}
    calls = []
    for request, case in zip(requests, ordered):
        assert request["prompt_version"].endswith(case["batch"])
        provider = [{k: v for k, v in e.items() if k in allowed} for e in events
            if e.get("event") == "weixin_chat" and e.get("trace_id") == request["trace_id"]]
        calls.append({"batch": case["batch"], "case_id": case["case_id"], "request_summary": request,
            "provider_calls": provider})
    write(OUT / "model-calls.json", {"source_log": str(log.relative_to(ROOT)),
        "requests": calls, "missing_provider_request": "v6 L04: retrieval dependency failure before LLM"})
    historical = VAR / "persona-live-20261012/run.json"
    original_hash = hashlib.sha256(historical.read_bytes()).hexdigest()
    assert original_hash == "d8a9a902afc233c08f2c17df2deb326b6bea72a83641b7f412e87b1bde652eea"
    manifest_path = OUT / "manifest.json"
    manifest = read(manifest_path) if manifest_path.exists() else {}
    manifest.update({"historical_18_run_sha256_unchanged": original_hash,
        "review_cases": len(cases), "real_persona_requests": len(requests),
        "model_configuration_changed": False, "ecs_deployed": False, "github_pushed": False,
        "external_rag_connected": False, "manual_audio_listening": "pending"})
    write(manifest_path, manifest)
    print(json.dumps({"cases": len(cases), "requests": len(requests), "output": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
