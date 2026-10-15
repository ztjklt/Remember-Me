"""Offline tests: never contact the local or external running services."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).with_name("live_acceptance.py")


def module():
    spec = importlib.util.spec_from_file_location("a01_persona_acceptance", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class AcceptanceSafety(unittest.TestCase):
    def test_prepare_is_offline_and_locks_exactly_eighteen_questions_without_answers(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "plan.json"
            completed = subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), "prepare", "--plan", str(output)],
                capture_output=True, text=True, encoding="utf8", cwd=ROOT)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            plan = json.loads(output.read_text(encoding="utf8"))
            self.assertEqual(len(plan["cases"]), 18)
            self.assertEqual([q["id"] for q in plan["cases"][:12]],
                ["Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07", "Q08", "U01", "U02", "A01", "N01"])
            self.assertTrue(all(set(q) == {"id", "mode", "role", "question"} for q in plan["cases"]))
            self.assertEqual(sum(q["mode"] == "persona" for q in plan["cases"]), 6)
            self.assertEqual({q["role"] for q in plan["cases"]}, {"owner", "reader"})
            self.assertEqual(len(plan["asr_basis"]), 10)
            self.assertNotIn("password", output.read_text(encoding="utf8"))

    def test_live_run_requires_explicit_ready_gate_before_reading_accounts(self):
        completed = subprocess.run([sys.executable, str(SCRIPT), "run"],
            capture_output=True, text=True, encoding="utf8", cwd=ROOT)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("--live-ready", completed.stderr)

    def test_failed_answer_is_retained_and_not_requested_again(self):
        mod = module()
        with tempfile.TemporaryDirectory() as directory:
            recorder = mod.Recorder(Path(directory) / "run.json", {"subject_id": "s"})
            state = {"subject_id": "s", "CLOUD_TWIN": "consent"}
            case = {"id": "Q01", "question": "question only", "role": "owner", "mode": "evidence"}
            calls = []
            def handler(request):
                calls.append(json.loads(request.content))
                return httpx.Response(503, json={"error_code": "TWIN_UNAVAILABLE"})
            with httpx.Client(base_url=mod.BASE, transport=httpx.MockTransport(handler)) as client:
                mod.run_case(recorder, {"owner": client}, case, state, {})
                mod.run_case(recorder, {"owner": client}, case, state, {})
            self.assertEqual(calls, [{"question": "question only", "mode": "evidence", "cloud_consent_id": "consent"}])
            self.assertEqual(recorder.data["items"][0]["status"], "failed")
            self.assertEqual(recorder.data["items"][0]["manual_review"]["grounding"]["rating"], "pending")

    def test_uncertain_started_answer_is_never_replayed(self):
        mod = module()
        with tempfile.TemporaryDirectory() as directory:
            recorder = mod.Recorder(Path(directory) / "run.json", {"subject_id": "s"})
            recorder.data["items"].append({"id": "Q01", "status": "started"})
            mod.run_case(recorder, {}, {"id": "Q01"}, {}, {})
            self.assertEqual(recorder.data["events"], [])

    def test_live_record_explicitly_labels_technical_fictional_review(self):
        mod = module()
        with tempfile.TemporaryDirectory() as directory:
            recorder = mod.Recorder(Path(directory) / "run.json", {"subject_id": "s"})
            self.assertIn("not actual person endorsement", recorder.data.get("review_basis", ""))

    def test_changed_asr_cannot_be_passed_as_the_same_evaluation(self):
        mod = module()
        plan = {"asr_basis": [{"episode_id": "e", "transcript_sha256": mod.text_digest("original ASR")} ]}
        with self.assertRaises(ValueError):
            mod.check_asr(plan, {"items": [{"episode_id": "e", "status": "ready", "transcript": "rewritten answer"}]})


if __name__ == "__main__":
    unittest.main()
