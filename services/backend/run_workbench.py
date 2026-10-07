"""Start real local adapters and workbench; never fall back to fake providers.

Run with a Python environment containing backend + AI Core dependencies and
sentence-transformers. Read .env locally; no credentials on the command line.
"""
import os
import subprocess
import sys
import time
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
AI_ROOT = ROOT.parent / 'ai-core'


def main():
    env = {**os.environ, **{k: v for k, v in dotenv_values(ROOT / '.env').items() if v is not None}}
    env.update(REMEMBER_STT_BACKEND='http', REMEMBER_AI_BACKEND='http', REMEMBER_ENABLE_WORKBENCH='true')
    cli = env.get('WHISPER_CLI')
    if cli:
        env['PATH'] = str(Path(cli).parent) + os.pathsep + env.get('PATH', '')
    env.setdefault('REMEMBER_STT_URL', 'http://127.0.0.1:8878')
    env.setdefault('REMEMBER_AI_CORE_URL', 'http://127.0.0.1:8879')
    env.setdefault('REMEMBER_STT_TIMEOUT_SECONDS', '300')
    env.setdefault('REMEMBER_AI_TIMEOUT_SECONDS', '90')
    env.setdefault('NO_PROXY', 'localhost,127.0.0.1,::1')
    ai_env = {**env, **{k: v for k, v in dotenv_values(AI_ROOT / '.env').items() if v is not None}}
    ai_env.setdefault('AI_PROVIDER', 'weixin')
    if ai_env['AI_PROVIDER'] == 'weixin':
        ai_env.setdefault('AI_BASE_URL', 'https://chatapi.weixin.qq.com/openai/v1')
        ai_env.setdefault('AI_MODEL', 'Deepseek-v4-flash')
        ai_env['AI_TIMEOUT_SECONDS'] = '45'
        ai_env['AI_MAX_CONCURRENT_REQUESTS'] = '1'
    ai_env.setdefault('AI_MODEL', 'deepseek-v4-flash')
    ai_env.setdefault('AI_MODEL_VERSION', ai_env['AI_MODEL'])
    (ROOT / 'var').mkdir(exist_ok=True)
    commands = [('backend', ROOT, env, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8877']),
                ('stt', ROOT, env, ['-m', 'uvicorn', 'app.local_stt:app', '--host', '127.0.0.1', '--port', '8878']),
                ('worker', ROOT, env, ['-m', 'app.worker']),
                ('profile-worker', ROOT, env, ['-m', 'app.profile_worker'])]
    key_name = 'WEIXIN_CHAT_API_KEY' if ai_env['AI_PROVIDER'] == 'weixin' else 'AI_API_KEY'
    if ai_env.get(key_name, '').strip():
        commands.append(('ai-core', AI_ROOT, ai_env, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8879']))
    else:
        print(key_name + ' missing: cloud extraction/Twin/profile proposals unavailable; local audio + STT remain usable.', flush=True)
    processes, logs = [], []
    try:
        for name, cwd, variables, args in commands:
            log = (ROOT / 'var' / (name + '.log')).open('a', encoding='utf-8')
            logs.append(log)
            processes.append(subprocess.Popen([sys.executable, *args], cwd=cwd, env=variables,
                stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
        print('Workbench: http://127.0.0.1:8877/workbench/ — Ctrl+C stops all child services.', flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(1)
        raise RuntimeError('A service stopped. Inspect services/backend/var/*.log; no fake fallback was started.')
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        for log in logs:
            log.close()


if __name__ == '__main__':
    main()
