"""One explicitly authorized native phase. No TTS, retry, emulator start or data reset.

Requires the existing local A01 backend, emulator-5554 and installed debug/test APKs.
Source material is the already generated immutable companion WAV; credentials never
appear in arguments, logs or result files. Runtime responses and screenshots persist.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
VAR = ROOT / "services/backend/var/a01-20261012"
SUBJECT = "subject_92b1690705074918a90981e5280a22c5"
WAV_SHA = "d7c9bf169a2d9e63decd5c1ab5faf889d70061fd8da30531150e78ed7d30527a"
PHASES = ["reader-create", "owner-accept", "reader-opt-in", "reader-question", "reader-withdraw", "owner-verify"]


def find_adb():
    executable = "adb.exe" if os.name == "nt" else "adb"
    for name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        sdk = os.environ.get(name)
        if sdk:
            candidate = Path(sdk) / "platform-tools" / executable
            if candidate.is_file():
                return candidate
    located = shutil.which("adb")
    if located:
        return Path(located)
    raise SystemExit("ADB not found; set ANDROID_HOME / ANDROID_SDK_ROOT or add adb to PATH.")


def adb(*args, data=None, timeout=360):
    return subprocess.run([str(find_adb()), "-s", "emulator-5554", *args], input=data,
                          capture_output=True, check=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=PHASES)
    parser.add_argument("--execute-authorized", action="store_true", required=True)
    parser.add_argument("--resume-submitted", action="store_true", help="Explicitly continue the already submitted note after inspected partial failure")
    parser.add_argument("--output", type=Path, default=VAR / "persona-android/native-write")
    args = parser.parse_args()
    destination = args.output / args.phase
    if destination.exists():
        raise SystemExit("Phase output already exists; inspect its real result before any explicit recovery.")
    if adb("get-state").stdout.strip() != b"device":
        raise SystemExit("Existing emulator-5554 is not ready; no new emulator will be launched.")
    accounts = json.loads((VAR / "private/local-accounts.json").read_text(encoding="utf-8"))
    role = "owner" if args.phase.startswith("owner") else "reader"
    config = {key: accounts[role][key] for key in ("username", "password")}
    config.update(phase=args.phase, execute_authorized=True, subject_id=SUBJECT, wav_sha256=WAV_SHA)
    if args.phase == "reader-create":
        wav = VAR / "voice-companion-live-20261012/materials/companion.wav"
        content = wav.read_bytes()
        if hashlib.sha256(content).hexdigest() != WAV_SHA:
            raise SystemExit("Immutable companion WAV hash mismatch.")
        # adb shell stdin can truncate binary at control bytes. Push first, then copy
        # under the app identity; the native test independently checks the exact SHA.
        adb("push", str(wav), "/data/local/tmp/persona-write-source.wav")
        adb("shell", "run-as", "me.remember.app", "cp", "/data/local/tmp/persona-write-source.wav", "files/persona-write-source.wav")
    else:
        created = json.loads((args.output / "reader-create/result.json").read_text(encoding="utf-8"))
        config["note_id"] = created["note_id"]
        if args.phase == "owner-accept" and not created.get("completed") and not args.resume_submitted:
            raise SystemExit("Reader create is incomplete. Inspect before mutating.")
    adb("shell", "run-as", "me.remember.app", "sh", "-c", '"cat > files/persona-write-login.json"',
        data=json.dumps(config, ensure_ascii=False).encode())
    destination.mkdir(parents=True)
    run = adb("shell", "am", "instrument", "-w", "-r", "-e", "class",
              "me.remember.app.PersonaCompanionWriteLiveTest",
              "me.remember.app.test/androidx.test.runner.AndroidJUnitRunner")
    output = run.stdout.decode("utf-8", errors="replace")
    (destination / "instrumentation.txt").write_text(output, encoding="utf-8")
    remote = f"/sdcard/Android/data/me.remember.app/files/persona-write/{args.phase}"
    listing = adb("shell", "ls", remote).stdout.decode().splitlines()
    for name in listing:
        if name.endswith((".json", ".png")) and "/" not in name:
            adb("pull", f"{remote}/{name}", str(destination / name))
    result = json.loads((destination / "result.json").read_text(encoding="utf-8"))
    print(json.dumps({key: result.get(key) for key in
                      ("phase", "completed", "note_id", "audio_id", "question_error", "failure")}, ensure_ascii=False))
    if "OK (1 test)" not in output or not result.get("completed"):
        raise SystemExit("Native phase failed; evidence preserved. No automatic retry.")


if __name__ == "__main__":
    main()
