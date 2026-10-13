"""The operator must not report a skipped or stale mobile run as accepted."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('ecs_ui_runner', Path(__file__).resolve().parents[3] / 'tools/round_two/two_device_ecs_check.py')
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


def test_junit_ok_does_not_override_skipped_instrumentation():
    with pytest.raises(RuntimeError):
        RUNNER.verify_instrumentation('INSTRUMENTATION_STATUS_CODE: 1\nINSTRUMENTATION_STATUS_CODE: -4\nOK (1 test)')


def test_success_requires_explicit_test_pass():
    RUNNER.verify_instrumentation('INSTRUMENTATION_STATUS_CODE: 1\nINSTRUMENTATION_STATUS_CODE: 0\nOK (1 test)')
    with pytest.raises(RuntimeError):
        RUNNER.verify_instrumentation('OK (1 test)')


def test_first_device_cleanup_failure_does_not_skip_other_inputs(tmp_path):
    private = tmp_path / 'private.json'; private.write_text('sensitive fixture')
    calls = []
    def adb(device, *args):
        calls.append(device)
        if device == 'first':
            raise RuntimeError('device offline')
    errors = RUNNER.cleanup_inputs(adb, ['first', 'second'], private)
    assert calls == ['first', 'second']
    assert not private.exists()
    assert len(errors) == 1 and 'first' in errors[0]


def test_completion_is_not_published_before_cleanup_even_when_report_write_fails(tmp_path):
    private = tmp_path / 'private.json'; private.write_text('sensitive fixture')
    report = {'phases_complete': True}
    attempted_states = []
    def adb(device, *args):
        assert not report.get('complete')
        raise RuntimeError('offline')
    def save():
        attempted_states.append(report.copy())
        raise OSError('disk full')
    with pytest.raises(RuntimeError, match='cleanup failed'):
        RUNNER.finish_report(report, adb, ['first'], private, save)
    assert not private.exists()
    assert attempted_states and all(not state.get('complete') for state in attempted_states)
