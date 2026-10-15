"""Last separately authorized v5 attempt; immutable audio and resumed actual ASR task.

Uses the versioned full-chain runner including the saved-text review before any
answer speech. Never resumes or overwrites a prior failed request.
"""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('a01_versioned_companion', Path(__file__).with_name('companion_regression_v4.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.VERSION = 'v5'
runner.EXPECTED_PROMPT = 'persona-conditional-reviewed-v5'
runner.OUT = runner.shared.VAR / 'companion-v5-regression-20261012'


if __name__ == '__main__':
    try:
        runner.main()
    except Exception as exc:
        raise SystemExit('Stopped (' + type(exc).__name__ + '); preserved v5 checkpoint; no further attempt') from None
