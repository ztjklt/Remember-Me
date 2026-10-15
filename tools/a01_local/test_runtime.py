import json
import importlib.util
from pathlib import Path


def test_proxy_cleanup_does_not_change_model_credential(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('a01_runtime',Path(__file__).with_name('runtime.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'VAR',tmp_path)
    (tmp_path/'private').mkdir()
    (tmp_path/'private/paraformer.json').write_text(json.dumps({'paraformer_api_key':'test-asr-only','paraformer_base_url':'https://example.invalid'}))
    monkeypatch.setattr(module,'dotenv_values',lambda path:{'WEIXIN_CHAT_API_KEY':'test-text-only'})
    monkeypatch.delenv('WEIXIN_CHAT_API_KEY',raising=False)
    monkeypatch.setenv('ALL_PROXY','socks5://localhost:1234')
    monkeypatch.setenv('SOME_LATE_ENV_NAME','should-never-be-a-key')
    output=module.configuration()
    assert output['WEIXIN_CHAT_API_KEY']=='test-text-only'
    assert output['REMEMBER_PARAFORMER_API_KEY']=='test-asr-only'
    assert not any(name.lower() in {'http_proxy','https_proxy','all_proxy'} for name in output)
    assert output['REMEMBER_AI_CORE_URL']=='http://127.0.0.1:8892'
