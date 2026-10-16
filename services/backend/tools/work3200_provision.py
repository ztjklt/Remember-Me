"""Generate a phone-scoped short-lived activation file without putting app_key in APKs.

Run with the backend Python environment. The request file is exported by the App.
The output contains a temporary vendor grant; transfer it privately to that phone.
"""
import argparse
import json
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pydantic import SecretStr
from app.config import Settings
from app.work3200 import issue_grant


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--business', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding='utf-8-sig'))
    if (request.get('version') != 1 or not re.fullmatch(r'rm-install-[a-f0-9-]{36}', request.get('device_id', ''))
            or not isinstance(request.get('user_id'), str) or not 1 <= len(request['user_id']) <= 128
            or request.get('server') != 'https://39.108.183.47'):
        parser.error('Invalid installation request or unexpected server.')
    if args.output.exists():
        parser.error('Output exists; choose a new filename to preserve the previous grant.')
    business = json.loads(args.business.read_text(encoding='utf-8-sig'))
    settings = Settings(_env_file=None, work3200_app_id=business['app_id'],
                        work3200_app_key=SecretStr(business['app_key']),
                        work3200_environment='DEVELOPMENT')
    grant = issue_grant(settings, request['user_id'], request['device_id'])
    grant['server'] = request['server']
    with args.output.open('x', encoding='utf-8') as file:
        json.dump(grant, file, ensure_ascii=False)
    print('Activation file written. Token expires (UTC):',
          datetime.fromtimestamp(grant['token_expire_time'], timezone.utc).isoformat())
    print('Business credentials were not included. Transfer this temporary file privately.')


if __name__ == '__main__':
    main()
