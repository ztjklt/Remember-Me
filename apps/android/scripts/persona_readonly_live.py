"""Authorized local Android read-only capture. No questions, TTS generation or content writes.

Installs nothing, starts no emulator, and does not reset app data. Credentials are
read from the private local account file and never printed or passed as arguments.
The native test consumes its temporary credential file before login.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
VAR = ROOT / "services/backend/var/a01-20261012"


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("owner", "reader"))
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--answer-id", default="")
    parser.add_argument("--asset-id", default="")
    parser.add_argument("--contribution-id", default="")
    parser.add_argument("--capture-folder", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    def adb(*parts, data=None, timeout=360):
        return subprocess.run([str(find_adb()), "-s", args.serial, *parts], input=data,
                              capture_output=True, check=True, timeout=timeout)

    if args.output.exists():
        raise SystemExit("Output exists; inspect it before any explicitly authorized recovery.")
    processes = adb("shell", "dumpsys", "activity", "processes").stdout.decode(errors="replace")
    if "ActiveInstrumentation{" in processes:
        raise SystemExit("Another instrumentation is running; no app interaction performed.")
    if adb("shell", "settings", "get", "system", "font_scale").stdout.strip() != b"1.0":
        raise SystemExit("This capture requires actual system font scale 1.0; no setting changed.")
    accounts = json.loads((VAR / "private/local-accounts.json").read_text(encoding="utf-8"))
    config = {key: accounts[args.role][key] for key in ("username", "password")}
    config.update(role=args.role, answer_id=args.answer_id, asset_id=args.asset_id,
                  contribution_id=args.contribution_id, capture_folder=args.capture_folder,
                  minimum_understandings=2, leave_open=False)
    adb("shell", "run-as", "me.remember.app", "sh", "-c", '"cat > files/persona-live-login.json"',
        data=json.dumps(config, ensure_ascii=False).encode())
    args.output.mkdir(parents=True)
    run = adb("shell", "am", "instrument", "-w", "-r", "-e", "class",
              "me.remember.app.PersonaReadOnlyLiveTest",
              "me.remember.app.test/androidx.test.runner.AndroidJUnitRunner")
    output = run.stdout.decode("utf-8", errors="replace")
    (args.output / "instrumentation.txt").write_text(output, encoding="utf-8")
    remote = f"/sdcard/Android/data/me.remember.app/files/{args.capture_folder}/{args.role}"
    listing = adb("shell", "ls", remote).stdout.decode().splitlines()
    for name in listing:
        if name.endswith((".json", ".png")) and "/" not in name:
            adb("pull", f"{remote}/{name}", str(args.output / name))
    if "OK (1 test)" not in output:
        raise SystemExit("Native capture failed; evidence preserved, no automatic retry.")
    print((args.output / "result.json").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
