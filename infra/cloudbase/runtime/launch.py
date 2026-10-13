"""CloudBase deployment entrypoint. No credentials are printed or put on argv."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[3]


def prepare_environment(source):
    env = dict(source)
    if any(str(env.get(key, '')).startswith('sk-sp-') for key in
            ('AI_API_KEY', 'WEIXIN_CHAT_API_KEY', 'REMEMBER_RELAY_ASR_API_KEY',
             'REMEMBER_PARAFORMER_API_KEY')):
        raise ValueError('Token Plan credentials are for interactive tools; use an application API credential here.')
    if env.get('REMEMBER_DEPLOYMENT_SCOPE') != 'ios-cloudbase':
        raise ValueError('Set the explicit ios-cloudbase deployment scope.')
    if not env.get('CLOUDBASE_ENV_ID', '').strip():
        raise ValueError('A dedicated CloudBase environment ID is required.')
    database = urlsplit(env.get('REMEMBER_DATABASE_URL', ''))
    if database.scheme != 'postgresql+psycopg' or not database.hostname or not database.path.strip('/'):
        raise ValueError('A dedicated PostgreSQL database is required.')
    database_options = dict(parse_qsl(database.query, keep_blank_values=True))
    database_options['options'] = '-csearch_path=remember_ios'
    database_options['sslmode'] = 'verify-full'
    public_ca = ROOT / 'infra/cloudbase/runtime/tencent-postgres-ca.crt'
    database_options['sslrootcert'] = ('/tmp/remember-postgres-ca.pem' if env.get('REMEMBER_POSTGRES_CA_PEM')
        else str(public_ca) if public_ca.is_file() else '/etc/ssl/certs/ca-certificates.crt')
    env['REMEMBER_DATABASE_URL'] = urlunsplit(database._replace(query=urlencode(database_options)))
    if env.get('REMEMBER_OBJECT_STORE_BACKEND') not in {'s3', 'cloudbase'}:
        raise ValueError('Raw audio and ASR checkpoints require persistent object storage.')
    if not env.get('REMEMBER_OBJECT_STORE_BUCKET', '').startswith('remember-me-ios-'):
        raise ValueError('Use an independent remember-me-ios-* private bucket.')
    if env['REMEMBER_OBJECT_STORE_BACKEND'] == 'cloudbase':
        env['REMEMBER_CLOUDBASE_ENVIRONMENT_ID'] = env['CLOUDBASE_ENV_ID']
        env['REMEMBER_CLOUDBASE_API_KEY'] = env.get('REMEMBER_CLOUDBASE_API_KEY') or env.get('CLOUDBASE_API_KEY', '')
        if not env['REMEMBER_CLOUDBASE_API_KEY']:
            raise ValueError('Supply this environment’s server-side CloudBase storage credential.')
    endpoint = urlsplit(env.get('REMEMBER_OBJECT_STORE_ENDPOINT_URL', ''))
    if env['REMEMBER_OBJECT_STORE_BACKEND'] == 's3' and (endpoint.scheme != 'https' or not endpoint.hostname or endpoint.username or endpoint.password
            or endpoint.query or endpoint.fragment or endpoint.path not in {'', '/'}
            or not endpoint.hostname.endswith('.myqcloud.com')):
        raise ValueError('Use the reviewed Tencent COS HTTPS endpoint.')
    if len(env.get('CLOUDBASE_WORKER_TOKEN', '')) < 32:
        raise ValueError('An independent worker credential of at least 32 characters is required.')
    if env.get('REMEMBER_STT_BACKEND') == 'paraformer':
        if not env.get('REMEMBER_PARAFORMER_API_KEY') or not env.get('REMEMBER_PARAFORMER_BASE_URL'):
            raise ValueError('Supply this environment’s own ASR configuration.')
    elif env.get('REMEMBER_STT_BACKEND') == 'relay':
        if (env.get('REMEMBER_RELAY_ASR_URL') != 'https://ai-router-cn-pub.anker-in.com/chat/completions'
                or env.get('REMEMBER_RELAY_ASR_MODEL') != 'hackathon/v_model/qwen-audio-3.0-asr-flash'
                or not env.get('REMEMBER_RELAY_ASR_API_KEY')):
            raise ValueError('Supply the explicitly selected Anker ASR endpoint, alias and credential.')
        env['REMEMBER_RELAY_ASR_CHECKPOINT_BACKEND'] = 'object_store'
        env['REMEMBER_RELAY_ASR_STATE_DIR'] = '/tmp/remember-asr'
    else:
        raise ValueError('Select an explicitly prepared ASR adapter.')
    if env.get('AI_PROVIDER') not in {'deepseek', 'weixin', 'anker'}:
        raise ValueError('Configure a real Twin provider; fixtures are not accepted.')
    key = 'WEIXIN_CHAT_API_KEY' if env['AI_PROVIDER'] == 'weixin' else 'AI_API_KEY'
    if not env.get(key):
        raise ValueError('Supply this environment’s own model credential.')
    # Defaults may never select SQLite, local originals, fake models or public registration.
    env.update(REMEMBER_ENVIRONMENT='staging', REMEMBER_ENABLE_WORKBENCH='false',
        REMEMBER_ALLOW_ACCOUNT_REGISTRATION='false', REMEMBER_ALLOW_FAKE_PROVIDERS='false',
        REMEMBER_AI_BACKEND='http', REMEMBER_AI_CORE_URL='http://127.0.0.1:8100',
        REMEMBER_PARAFORMER_CHECKPOINT_BACKEND='object_store',
        REMEMBER_PARAFORMER_STATE_DIR='/tmp/remember-asr',
        REMEMBER_MAX_UPLOAD_BYTES=str(18 * 1024 * 1024))
    # Each request completes before returning. No detached processing loops.
    env['REMEMBER_AI_TIMEOUT_SECONDS'] = str(min(float(env.get('REMEMBER_AI_TIMEOUT_SECONDS', 40)), 40))
    env['AI_TIMEOUT_SECONDS'] = str(min(float(env.get('AI_TIMEOUT_SECONDS', 40)), 40))
    env['REMEMBER_PARAFORMER_POLL_TIMEOUT_SECONDS'] = '20'
    env['REMEMBER_STT_TIMEOUT_SECONDS'] = '40' if env['REMEMBER_STT_BACKEND'] == 'relay' else '8'
    env['AI_MAX_CONCURRENT_REQUESTS'] = '1'
    env['NO_PROXY'] = '127.0.0.1,localhost'
    return env


def command(role, port='8000'):
    backend = ROOT / 'services/backend'
    ai = ROOT / 'services/ai-core'
    if role == 'ai':
        return ai, [str(ai / '.venv/bin/python'), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8100', '--workers', '1', '--no-access-log']
    if role == 'api':
        return backend, [str(backend / '.venv/bin/python'), '-m', 'uvicorn', 'runtime.api:app', '--host', '0.0.0.0', '--port', port, '--workers', '1', '--no-access-log', '--ws', 'wsproto', '--ws-ping-interval', '0', '--proxy-headers', '--forwarded-allow-ips', '*']
    if role == 'migrate':
        return backend, [str(backend / '.venv/bin/alembic'), 'upgrade', 'head']
    raise ValueError('Unknown process role.')


def serve(env):
    port = int(env.get('PORT', '8000'))
    if not 1 <= port <= 65535 or port == 8100:
        raise ValueError('Invalid HTTP port.')
    children = []
    stopping = False
    def stop(_signal=None, _frame=None):
        nonlocal stopping
        stopping = True
        for process in children:
            if process.poll() is None:
                process.terminate()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    env['PYTHONPATH'] = str(ROOT / 'infra/cloudbase')
    try:
        cwd, argv = command('ai')
        ai = subprocess.Popen(argv, cwd=cwd, env=env)
        children.append(ai)
        deadline = time.monotonic() + 45
        while not stopping:
            if ai.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('AI service did not become healthy.')
            try:
                with urlopen('http://127.0.0.1:8100/health', timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.2)
        if stopping:
            return 0
        cwd, argv = command('api', str(port))
        children.append(subprocess.Popen(argv, cwd=cwd, env=env))
        while not stopping:
            for process in children:
                if process.poll() is not None:
                    return process.returncode or 1
            time.sleep(0.2)
        return 0
    finally:
        stop()
        for process in children:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def main():
    try:
        env = prepare_environment(os.environ)
        if env.get('REMEMBER_POSTGRES_CA_PEM'):
            ca = Path('/tmp/remember-postgres-ca.pem')
            ca.write_text(env['REMEMBER_POSTGRES_CA_PEM'])
            ca.chmod(0o600)
        action = sys.argv[1] if len(sys.argv) > 1 else 'serve'
        if action == 'serve':
            return serve(env)
        if action == 'migrate':
            cwd, argv = command('migrate')
            return subprocess.call(argv, cwd=cwd, env=env)
        if action == 'account-create' and len(sys.argv) == 4:
            cwd = ROOT / 'services/backend'
            return subprocess.call([str(cwd / '.venv/bin/python'), '-m', 'app.account_admin',
                'create', sys.argv[2], '--name', sys.argv[3]], cwd=cwd, env=env)
        raise ValueError('Use serve, migrate, or account-create USER DISPLAY_NAME.')
    except (ValueError, RuntimeError) as error:
        # Messages above contain field names only, never input values.
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
