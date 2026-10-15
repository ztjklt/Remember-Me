"""Extract memories from actual LLM corrected drafts, never authored replacements."""
import argparse
import json
import sys
import time
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/ai-core"))
from app.providers.weixin import WeixinProvider, MODEL
from app.extractor import MemoryExtractor
from app.contracts import AICoreInput


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    output = args.run / "downstream"
    output.mkdir(exist_ok=False)
    key = dotenv_values("D:/codex_work/remember-me-agent-loop/services/ai-core/.env").get("WEIXIN_CHAT_API_KEY")
    provider = WeixinProvider(api_key=key)
    extractor = MemoryExtractor(provider=provider, model=MODEL, model_version=MODEL)
    try:
        for name in ("A01_02", "A01_08"):
            source = json.loads((args.run / (name + ".json")).read_text(encoding="utf-8"))
            assert source["status"] == "completed"
            result = {"case_id":name, "input":"actual_automatic_correction_draft",
                      "transcript":source["result"]["draft"], "human_review":False}
            started = time.perf_counter()
            try:
                answer = extractor.process(AICoreInput(episode_id=name, subject_id="proofread-fictional",
                    transcript=result["transcript"], existing_model_version="model-v0"))
                result.update(status="completed", output=answer.model_dump(mode="json"))
            except Exception as exc:
                result.update(status="failed", error_type=type(exc).__name__)
            result["seconds"] = round(time.perf_counter()-started, 3)
            (output / (name + ".json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(name, result["status"], flush=True)
    finally:
        provider.close()


if __name__ == "__main__":
    main()
