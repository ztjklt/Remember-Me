"""Deploy as a private timer-triggered Python cloud function; no HTTP trigger."""
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'Redirect refused.', headers, fp)


def main_handler(event, context):
    base = os.environ['REMEMBER_IOS_API_URL'].rstrip('/')
    parsed = urlsplit(base)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path):
        raise ValueError('Configure the exact reviewed API HTTPS origin.')
    token = os.environ['CLOUDBASE_WORKER_TOKEN']
    if len(token) < 32:
        raise ValueError('A worker credential is required.')
    opener = urllib.request.build_opener(NoRedirect)
    # Each operation finishes within its request; the provider checkpoints and
    # job leases survive a killed request. No task continues after this returns.
    for operation in ('processing-tick', 'profile-tick'):
        request = urllib.request.Request(base + '/internal/jobs/' + operation,
            method='POST', data=b'', headers={'Authorization':'Bearer ' + token})
        try:
            with opener.open(request, timeout=55) as response:
                if response.status != 200:
                    raise RuntimeError('A worker tick did not finish.')
        except urllib.error.HTTPError as error:
            if error.code != 409:
                raise RuntimeError('A worker tick was rejected; inspect private service logs.') from None
    return {'timer_completed': True}
