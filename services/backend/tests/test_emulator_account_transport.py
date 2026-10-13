from types import SimpleNamespace
import pytest
from starlette.requests import Request
from app.api.accounts import transport
from app.errors import RequestInvalid


@pytest.mark.parametrize('environment,peer,allowed,success',[
    ('development','127.0.0.1',True,True),
    ('development','127.0.0.1',False,False),
    ('development','198.51.100.5',True,False),
    ('production','127.0.0.1',True,False),
])
def test_emulator_login_requires_local_peer_dev_and_explicit_host(environment,peer,allowed,success):
    settings=SimpleNamespace(environment=environment,allowed_hosts=['10.0.2.2'] if allowed else ['127.0.0.1'])
    app=SimpleNamespace(state=SimpleNamespace(settings=settings))
    request=Request({'type':'http','scheme':'http','path':'/api/v1/accounts/login','query_string':b'',
        'server':('10.0.2.2',8891),'client':(peer,45678),
        'headers':[(b'host',b'10.0.2.2:8891')],'app':app})
    if success:transport(request)
    else:
        with pytest.raises(RequestInvalid):transport(request)
