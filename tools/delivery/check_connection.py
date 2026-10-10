"""Check demo HTTPS and optionally login without writing credentials or tokens.

Run from a teammate's actual network. This does not call ASR/LLM or change the
allowlist. Passing means connectivity/auth only, not full product acceptance.
"""
import argparse
import getpass
import json
from pathlib import Path
import ssl
import urllib.request
import urllib.error

SERVER = 'https://39.108.183.47'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--login', metavar='USERNAME')
    parser.add_argument('--external-boundaries', action='store_true', help='Also require named blog hosts to reject this non-allowlisted external network')
    parser.add_argument('--certificate', type=Path, default=Path(__file__).resolve().parents[2] / 'apps/android/app/src/internal/res/raw/remember_ecs_ip_demo.pem')
    args = parser.parse_args()
    context = ssl.create_default_context(cafile=str(args.certificate))
    # Avoid inheriting an unrelated proxy; use the same direct route as the APK.
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context), NoRedirect())

    def request(path, body=None, token=None):
        headers = {'Cache-Control': 'no-store'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if body is not None:
            headers['Content-Type'] = 'application/json'
        payload = json.dumps(body).encode() if body is not None else None
        with client.open(urllib.request.Request(SERVER + path, data=payload, headers=headers), timeout=20) as response:
            return json.load(response)

    def denied(path, status, body=None, host=None, required_message=None):
        headers = {'Content-Type': 'application/json'}
        if host:
            headers['Host'] = host
        payload = json.dumps(body).encode() if body is not None else None
        try:
            with client.open(urllib.request.Request(SERVER + path, data=payload, headers=headers), timeout=20):
                raise RuntimeError('A protected operation unexpectedly succeeded')
        except urllib.error.HTTPError as error:
            if error.code != status:
                raise RuntimeError('A protected operation returned an unexpected status') from None
            if required_message and required_message not in error.read().decode('utf-8'):
                raise RuntimeError('Registration was not rejected for the expected reason')

    try:
        info = request('/api/v1/service-info')
        if info.get('api_version') != '0.7.0':
            raise RuntimeError('API version does not match this APK')
        result = {'server': SERVER, 'https_verified': True, 'service': info, 'scope': 'connectivity only'}
        if info.get('registration_allowed') is not False:
            raise RuntimeError('Demo registration must remain closed')
        denied('/api/v1/workbench/spaces', 401)
        denied('/api/v1/accounts/register', 422, {'username': 'connectivity_probe_no_account', 'password': 'not-a-real-account-20261010', 'display_name': 'closed registration probe'}, required_message='尚未开放注册')
        result['unauthenticated_data_denied'] = True
        result['registration_denied'] = True
        if args.external_boundaries:
            for host in ('skyspace.cloud', 'www.skyspace.cloud'):
                denied('/', 403, host=host)
            result['named_blog_denied_from_external_network'] = True
        if args.login:
            login = request('/api/v1/accounts/login', {'username': args.login, 'password': getpass.getpass('Password: ')})
            token = login['actor_token']
            try:
                spaces = request('/api/v1/workbench/spaces', token=token)
                result.update(login_verified=True, spaces_count=len(spaces['items']))
            finally:
                request('/api/v1/accounts/logout', {}, token=token)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        # Exceptions can contain request details: only report the type, not secrets.
        print(json.dumps({'passed': False, 'error_type': type(error).__name__, 'action': 'Check network allowlist, certificate/device date, then account with administrator.'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
