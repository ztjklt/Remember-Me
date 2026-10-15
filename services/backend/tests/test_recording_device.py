import json
import time
from pathlib import Path
import httpx
from pydantic import SecretStr
from app.seed import seed_development_data
from app.soundcore_device import authenticate, DeviceAuthUnavailable

INSTALLATION='00000000-0000-0000-0000-000000000001'

def configured(app):
    app.state.settings.soundcore_app_id='qa-public-app-id'
    app.state.settings.soundcore_app_key=SecretStr('synthetic-vendor-secret-never-return')


def good(request):
    assert request.url.host=='speaker-api-ci.anker-in.com'
    assert request.headers['X-Product-Code']=='D3200'
    assert request.headers['X-Soundcore-SDK-Version']=='V1.3.01'
    assert 'Authorization' not in request.headers
    body=json.loads(request.content)
    return httpx.Response(200,json={'code':1,'message':'success','data':{
        'token':'synthetic-short-lived-token','token_expire_time':int(time.time())+3600,
        'license':{k:body[k] for k in ('app_id','user_id','device_id')},'license_signature':'synthetic-signature'}})


def test_sdk_session_is_owner_scoped_cached_and_keeps_key_on_server(app,client,session):
    configured(app);seen=[]
    def vendor(request):seen.append(request);return good(request)
    app.state.soundcore_http_transport=httpx.MockTransport(vendor)
    own=seed_development_data(session,subject_name='QA',actor_name='QA')
    other=seed_development_data(session,subject_name='Other',actor_name='Other')
    headers={'Authorization':'Bearer '+own.actor_token}
    url=f'/api/v1/subjects/{own.subject_id}/recording-device/session'
    assert client.post(url,headers={'Authorization':'Bearer '+other.actor_token},json={'installation_id':INSTALLATION}).status_code==404
    assert not seen
    response=client.post(url,headers=headers,json={'installation_id':INSTALLATION})
    assert response.status_code==200,response.text
    assert response.headers['cache-control']=='no-store'
    data=response.json()
    import jsonschema
    schema=Path(__file__).resolve().parents[3]/'packages/contracts/schemas/recording-device-v1.schema.json'
    jsonschema.validate(data,json.loads(schema.read_text()))
    assert data['user_id']==own.actor_id and data['device_id'].startswith('rm_')
    assert 'synthetic-vendor-secret' not in response.text and 'app_key' not in response.text
    assert json.loads(data['license_json'])['device_id']==data['device_id']
    assert client.post(url,headers=headers,json={'installation_id':INSTALLATION}).json()==data
    assert len(seen)==1
    assert client.post(url,headers=headers,json={'installation_id':INSTALLATION,'origin':'https://other.invalid'}).status_code==422


def test_missing_vendor_config_has_usable_fallback(app,client,session):
    own=seed_development_data(session,subject_name='QA',actor_name='QA')
    headers={'Authorization':'Bearer '+own.actor_token}
    prefix=f'/api/v1/subjects/{own.subject_id}/recording-device'
    assert client.get(prefix+'/capabilities',headers=headers).json()['available'] is False
    assert client.post(prefix+'/session',headers=headers,json={'installation_id':INSTALLATION}).status_code==503


def test_vendor_redirect_scope_mismatch_and_business_error_are_closed(app):
    import pytest
    configured(app)
    responses=[httpx.Response(302,headers={'Location':'https://other.invalid'}),
        httpx.Response(200,json={'code':1,'data':{'token':'private-token','token_expire_time':int(time.time())+3600,'license':{'app_id':'wrong'},'license_signature':'private-signature'}}),
        httpx.Response(200,json={'code':0,'message':'private-vendor-response'})]
    for response in responses:
        with pytest.raises(DeviceAuthUnavailable) as failure:
            authenticate(app.state.settings,'qa-actor',INSTALLATION,transport=httpx.MockTransport(lambda _:response))
        assert 'private' not in str(failure.value)
