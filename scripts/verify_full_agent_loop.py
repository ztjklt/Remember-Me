#!/usr/bin/env python3
"""Opt-in live software acceptance: synthetic Mac speech, Whisper, BGE, real AI.

Run with backend's retrieval extra installed. Credentials are read only by the
AI service from --env-file; output contains solely synthetic test material.
No microphone, phone, existing database, or real user's records are touched.
"""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def ai_server(args):
    sys.path.insert(0, str(ROOT / "services/ai-core"))
    from app.api import create_app
    from app.config import Settings
    from app.prompts import PROMPT_VERSION, SCHEMA_VERSION
    import uvicorn
    settings = Settings(_env_file=args.env_file, provider="deepseek", model="deepseek-flash",
                        model_version="deepseek-flash-live", base_url="https://api.deepseek.com",
                        timeout_seconds=90, prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION)
    uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, log_level="warning")


def verify(args):
    import httpx
    sys.path.insert(0, str(ROOT / "services/backend"))
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from app.config import Settings
    from app.main import create_app
    from app.models import MemoryItem, PersonTrait
    from app.seed import seed_development_data
    from app.stt import Transcript
    from app.worker import ProcessingWorker
    from app.local_stt import transcribe_audio

    class LocalWhisper:
        def transcribe(self, audio, content_type):
            result = transcribe_audio(audio)
            return Transcript(text=result["text"], backend="local-whisper", model_version=result["model_version"])

    output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    server_log = (output / "ai-server.log").open("w")
    process = subprocess.Popen([str(ROOT / "services/ai-core/.venv/bin/python"), str(Path(__file__).resolve()),
                                "ai-server", "--env-file", args.env_file, "--port", str(port)],
                               stdout=server_log, stderr=server_log)
    report = {"synthetic_source_audio": True, "physical_device": False, "checks": [], "episodes": []}
    try:
        url = f"http://127.0.0.1:{port}"
        for _ in range(100):
            if process.poll() is not None: raise RuntimeError("Live AI service could not start; inspect ai-server.log")
            try:
                if httpx.get(url + "/health", timeout=1, trust_env=False).status_code == 200: break
            except httpx.HTTPError: pass
            time.sleep(.1)
        else: raise RuntimeError("AI service startup timed out")
        with tempfile.TemporaryDirectory(prefix="remember-full-loop-") as folder:
            database = "sqlite:///" + str(Path(folder) / "acceptance.db")
            config = Config(str(ROOT / "services/backend/alembic.ini"))
            config.set_main_option("script_location", str(ROOT / "services/backend/migrations"))
            config.set_main_option("sqlalchemy.url", database)
            command.upgrade(config, "head")
            settings = Settings(_env_file=None, environment="test", log_level="WARNING", database_url=database,
                                object_store_backend="memory", stt_backend="http", ai_backend="http",
                                ai_core_url=url, ai_timeout_seconds=100)
            app = create_app(settings)
            with TestClient(app) as client:
                app.state.stt_provider = LocalWhisper()
                with app.state.database.session() as session:
                    own = seed_development_data(session, subject_name="合成测试人物", actor_name="合成测试操作者")
                headers = {"Authorization": "Bearer " + own.actor_token}
                base = f"/api/v1/subjects/{own.subject_id}"
                worker = ProcessingWorker(app.state.database, app.state.object_store, app.state.stt_provider,
                                          app.state.ai_client, max_attempts=1, lease_seconds=300, backoff_seconds=0)

                def check(name, condition, detail=None):
                    report["checks"].append({"name": name, "passed": bool(condition), "detail": detail})
                    print(json.dumps({"check": name, "passed": bool(condition)}, ensure_ascii=False), flush=True)

                def get(path):
                    response = client.get(path, headers=headers)
                    response.raise_for_status(); return response.json()

                def post(path, body):
                    response = client.post(path, headers=headers, json=body)
                    if response.status_code >= 400: raise RuntimeError(f"{path}: {response.status_code} {response.text}")
                    return response.json()

                def capture(key, text, metadata=None):
                    audio_path = output / (key + ".aiff")
                    subprocess.run(["say", "-v", "Tingting", "-r", "165", "-o", str(audio_path), text], check=True, capture_output=True)
                    m4a = output / (key + ".m4a")
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(audio_path), "-c:a", "aac", str(m4a)], check=True, capture_output=True)
                    data = {"subject_id": own.subject_id, "recording_consent_id": own.consent_id,
                            "idempotency_key": key, "source": "IOS_MIC", "recorded_at": "2026-10-08T09:00:00Z", "audio_ref": key + ".m4a"}
                    if metadata: data["metadata"] = json.dumps(metadata)
                    uploaded = client.post("/api/v1/episodes", headers=headers, data=data,
                                           files={"file": (key + ".m4a", m4a.read_bytes(), "audio/mp4")})
                    uploaded.raise_for_status(); episode = uploaded.json()["episode_id"]
                    worker.run_once()
                    review = get(f"/api/v1/episodes/{episode}/transcript-review")
                    check(key + ": real STT reached human review", review["state"] == "reviewing")
                    # This is deliberate fixture confirmation, not a claim that
                    # raw ASR was perfect or a human subject actually consented.
                    confirmed = client.patch(f"/api/v1/episodes/{episode}/transcript-review", headers=headers, json={"transcript": text})
                    confirmed.raise_for_status()
                    worker.run_once(); worker.run_once()
                    status = get(f"/api/v1/episodes/{episode}")
                    check(key + ": extraction and model committed", status["status"] == "ready", status)
                    if status["status"] != "ready": raise RuntimeError("Live model processing failed")
                    result = get(f"/api/v1/episodes/{episode}/result")
                    report["episodes"].append({"key": key, "episode_id": episode, "confirmed_transcript": text,
                                               "raw_asr": review["transcript"], "stt_model_version": review["stt_model_version"], "result": result})
                    return episode

                capture("initial", "我叫林青，在杭州做软件工程师。姐姐林月是我最信任的人。去年我和姐姐在公园散步，听见树叶沙沙响，那天我有些疲倦，但是很安心。我平时喜欢喝咖啡。做重大决定时，我先查预算，再和家人商量。家庭陪伴对我比赚更多钱重要。我习惯说短句，喜欢直接说结论。现在回想那次散步，记忆里是一种温暖柔和的色彩。")
                initial = get(base + "/person-model")
                check("all seven domains receive grounded understanding", all(d["traits"] for d in initial["domains"]), [d["domain"] for d in initial["domains"] if d["traits"]])
                capture("support", "我平时还是喜欢喝咖啡，这个喜好和以前一样。")
                supported = get(base + "/person-model")
                preference = next(d["traits"] for d in supported["domains"] if d["domain"] == "PREFERENCES")
                check("independent episode supports a durable trait", any(len(t["memory_item_ids"]) >= 2 for t in preference), preference)
                cloud = post("/api/v1/consents", {"subject_id": own.subject_id, "scope": "CLOUD_TWIN"})["consent_id"]
                answer = post(base + "/twin/answers", {"question": "我平时喜欢喝哪种饮品？", "cloud_consent_id": cloud})
                report["locked_twin"] = answer
                check("Twin answers an unseen question from evidence", answer["response_type"] != "UNKNOWN" and bool(answer["evidence"]), answer)
                if answer["response_type"] == "UNKNOWN": raise RuntimeError("Twin could not answer a supported question")
                locked = post(base + "/calibrations", {"twin_answer_id": answer["answer_id"], "cloud_consent_id": cloud})
                capture("human", "以前我喜欢咖啡，但现在我只喜欢喝茶。我选茶是因为它更温和。我会先考虑舒不舒服，再考虑价格。现在我更珍惜平静的状态，喝茶时觉得放松。我会简单地说，茶更适合现在的我。", {"calibration_id": locked["calibration_id"]})
                comparison = post(base + f'/calibrations/{locked["calibration_id"]}/complete', {"cloud_consent_id": cloud})
                report["calibration"] = comparison
                check("five-dimension compare preserves original locked answer", len(comparison["dimensions"]) == 5 and comparison["locked_answer"] == locked["locked_answer"], comparison)
                after = get(base + "/person-model")
                report["person_model"] = after
                check("explicit change retires the old preference", any(t["status"] == "superseded" for d in after["domains"] if d["domain"] == "PREFERENCES" for t in d["traits"]))
                questions = get(base + "/questions")["items"]
                report["next_questions"] = questions
                followup = next((q for q in questions if q["reason"] == "calibration_gap"), None)
                check("comparison drives next guided capture", followup is not None and bool(followup["evidence_ids"]), questions)
                if followup:
                    capture("follow-up", "在选择饮品时，我最在意喝完是否舒服。温和对我比便宜更重要，我也会先比较价格，然后再决定。", {"question_id": followup["question_id"]})
                    check("next capture updates understanding and advances plan", get(base + "/person-model")["version"] > after["version"])
                current = post(base + "/twin/answers", {"question": "我现在最喜欢喝哪种饮品？", "cloud_consent_id": cloud})
                report["current_twin"] = current
                check("new Twin answer uses corrected current preference", "茶" in current["answer"] and current["response_type"] != "UNKNOWN", current)
                facets = {facet["category"] for episode in report["episodes"] for memory in episode["result"]["memory_items"] for facet in memory.get("metadata", {}).get("facets", [])}
                report["facet_categories"] = sorted(facets)
                observations = any(m.get("metadata", {}).get("audio_observation", {}).get("status") == "available"
                                   for e in report["episodes"] for m in e["result"]["memory_items"])
                # Status has two evidence paths: an explicit self-description
                # or actual signal measurements. Do not require the LLM to
                # invent a textual state when signal data is already available.
                views = {"thing": any(m["memory_type"] == "EVENT" for e in report["episodes"] for m in e["result"]["memory_items"]),
                         **{name: name in facets for name in ("mood", "psychology", "filter", "environment", "identity", "expression")},
                         "status": "status" in facets or observations}
                report["portrait_views"] = views
                check("eight portrait views have evidence or signal observations", all(views.values()), views)
                check("real audio signal observation available", observations)
    except Exception as exc:
        report["error"] = str(exc)
        print("Live evaluation failed; see report.json", flush=True)
    finally:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
        server_log.close()
        report["passed"] = "error" not in report and all(c["passed"] for c in report["checks"])
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("ai-server", "verify"))
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--port", type=int, default=18100)
    parser.add_argument("--output", default="build/full-agent-loop-live")
    options = parser.parse_args()
    if options.mode == "ai-server": ai_server(options)
    else: sys.exit(verify(options))
