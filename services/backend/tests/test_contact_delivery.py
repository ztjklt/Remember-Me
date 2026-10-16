"""Provider request/exception checks; no real providers or destinations used."""
import base64
import hashlib
import hmac
import json
from urllib.parse import quote
from pydantic import SecretStr
import pytest
from app.contact_delivery import ContactDelivery, DeliveryUnavailable, public_origin


def test_sms_posts_approved_template_and_signature_without_query_leak(settings,monkeypatch):
    settings.contact_sms_access_key_id='test-ak'
    settings.contact_sms_access_key_secret=SecretStr('test-secret')
    settings.contact_sms_sign_name='TestSign'
    settings.contact_sms_code_template='SMS_TEST'
    sent=[]
    class Http:
        def __init__(self,**kwargs): assert kwargs['follow_redirects'] is False
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def post(self,url,data):
            sent.append((url,data))
            class Response:
                status_code=200
                def json(self): return {'Code':'OK'}
            return Response()
    monkeypatch.setattr('app.contact_delivery.httpx.Client',Http)
    ContactDelivery(settings).send('sms','+8613800138000',code='123456')
    url,body=sent[0];assert url=='https://dysmsapi.aliyuncs.com/'
    assert body['PhoneNumbers']=='13800138000' and body['TemplateCode']=='SMS_TEST'
    assert json.loads(body['TemplateParam'])=={'code':'123456'}
    signature=body.pop('Signature')
    encode=lambda x:quote(str(x),safe='~')
    canonical='&'.join(encode(k)+'='+encode(v) for k,v in sorted(body.items()))
    expected=base64.b64encode(hmac.new(b'test-secret&',('POST&%2F&'+encode(canonical)).encode(),hashlib.sha1).digest()).decode()
    assert signature==expected


def test_provider_timeout_sanitized_and_not_retried(settings,monkeypatch):
    provider=ContactDelivery(settings);attempts=[]
    monkeypatch.setattr(provider,'available',lambda *a,**k:True)
    def timeout(*a,**k):
        attempts.append(1);raise TimeoutError('password=test-secret&code=123456&recipient=private')
    monkeypatch.setattr(provider,'_email',timeout)
    with pytest.raises(DeliveryUnavailable) as error: provider.send('email','family@example.test',code='123456')
    assert len(attempts)==1 and '123456' not in str(error.value) and 'test-secret' not in str(error.value)


@pytest.mark.parametrize('origin',['http://public.example.test','https://user:pass@example.test','https://example.test/path','https://example.test/#token'])
def test_only_valid_public_origin_can_issue_links(settings,origin):
    settings.contact_entrustment_public_url=origin
    with pytest.raises(DeliveryUnavailable):public_origin(settings)


def test_smtp_uses_starttls_login_and_plaintext_safe_message(settings,monkeypatch):
    settings.contact_smtp_host='smtp.example.test';settings.contact_smtp_username='test'
    settings.contact_smtp_password=SecretStr('test-secret');settings.contact_smtp_from='sender@example.test'
    settings.contact_smtp_tls='starttls';settings.contact_smtp_port=587
    calls=[]
    class SMTP:
        def __init__(self,host,port,**kwargs): assert host=='smtp.example.test' and port==587
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def starttls(self,context):calls.append('tls')
        def login(self,*args):calls.append('login')
        def send_message(self,mail):
            calls.append('send');assert mail['To']=='family@example.test'
            assert '123456' in mail.get_content() and mail.get_content_type()=='text/plain'
            return {}
    monkeypatch.setattr('app.contact_delivery.smtplib.SMTP',SMTP)
    ContactDelivery(settings).send('email','family@example.test',code='123456')
    assert calls==['tls','login','send']
