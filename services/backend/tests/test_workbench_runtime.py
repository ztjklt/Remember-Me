from run_workbench import prepare_runtime


def test_default_runtime_never_starts_whisper():
    env, ai, commands = prepare_runtime({'WEIXIN_CHAT_API_KEY': 'test-key'}, {})
    assert env['REMEMBER_STT_BACKEND'] == 'relay'
    assert not any('app.local_stt:app' in command[-1] for command in commands)
    assert ai['AI_BASE_URL'] == 'https://chatapi.weixin.qq.com/openai/v1'
    assert ai['AI_MODEL'] == 'Deepseek-v4-flash'


def test_local_sidecar_requires_explicit_legacy_opt_in():
    for selected in ('http', 'relay'):
        _, _, commands = prepare_runtime({'REMEMBER_STT_BACKEND': selected}, {})
        assert not any('app.local_stt:app' in c[-1] for c in commands)
    _, _, commands = prepare_runtime({'REMEMBER_STT_BACKEND': 'http', 'REMEMBER_START_LOCAL_STT': 'true'}, {})
    assert any('app.local_stt:app' in c[-1] for c in commands)
