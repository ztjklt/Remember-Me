"""Private contact delivery adapters; never log destinations, codes or credentials."""
import base64
import hashlib
import hmac
import json
import re
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import quote, urlsplit
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet, InvalidToken
from .errors import AppError, RequestInvalid
from .models import utcnow


class DeliveryUnavailable(AppError):
    code = 'CONTACT_DELIVERY_UNAVAILABLE'
    http_status = 503


def normalize_contact(channel, contact):
    value = contact.strip()
    if channel == 'sms':
        value = re.sub(r'[ ()-]', '', value)
        if value.startswith('0086'): value = '+' + value[2:]
        if re.fullmatch(r'1[3-9][0-9]{9}', value): value = '+86' + value
        if not re.fullmatch(r'\+861[3-9][0-9]{9}', value):
            raise RequestInvalid('请输入中国大陆手机号。')
    elif channel == 'email':
        if len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value):
            raise RequestInvalid('请输入有效邮箱地址。')
        local, domain = value.rsplit('@', 1)
        if len(local) > 64 or local.startswith('.') or local.endswith('.') or '..' in value:
            raise RequestInvalid('请输入有效邮箱地址。')
        value = local.lower() + '@' + domain.lower()
    else:
        raise RequestInvalid('请选择邮箱或手机号。')
    return value


def mask_contact(channel, value):
    if channel == 'sms': return value[:6] + '****' + value[-4:]
    local, domain = value.split('@', 1)
    return local[:1] + '***@' + domain


class ContactVault:
    def __init__(self, settings):
        try:
            key = settings.contact_entrustment_key.get_secret_value().encode('ascii')
            self.fernet = Fernet(key)
            self.key = base64.urlsafe_b64decode(key)
        except (ValueError, UnicodeError):
            raise DeliveryUnavailable('托付服务尚未配置，请联系服务管理员。') from None

    def digest(self, domain, value):
        return hmac.new(self.key, (domain + '\0' + value).encode(), hashlib.sha256).hexdigest()

    def encrypt(self, value):
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt(self, value):
        try: return self.fernet.decrypt(value.encode()).decode()
        except (InvalidToken, ValueError):
            raise DeliveryUnavailable('托付配置已变化，请联系服务管理员恢复。') from None


def public_origin(settings):
    value = settings.contact_entrustment_public_url.rstrip('/')
    parsed = urlsplit(value)
    local = settings.environment in {'test', 'development'} and parsed.hostname in {'localhost', '127.0.0.1', 'testserver'}
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path or (parsed.scheme != 'https' and not (local and parsed.scheme == 'http'))):
        raise DeliveryUnavailable('托付领取网址尚未配置。')
    return value


class ContactDelivery:
    def __init__(self, settings): self.settings = settings

    def available(self, channel, *, notice=False):
        s = self.settings
        if channel == 'email':
            return bool(s.contact_smtp_host and s.contact_smtp_username and s.contact_smtp_password.get_secret_value()
                        and s.contact_smtp_from)
        if channel == 'sms':
            template = s.contact_sms_notice_template if notice else s.contact_sms_code_template
            return bool(s.contact_sms_access_key_id and s.contact_sms_access_key_secret.get_secret_value()
                        and s.contact_sms_sign_name and template)
        return False

    def send(self, channel, contact, *, code=None, link=None):
        if not self.available(channel, notice=link is not None):
            raise DeliveryUnavailable('该接收方式尚未配置发送服务。')
        try:
            if channel == 'email': self._email(contact, code=code, link=link)
            else: self._sms(contact, code=code, link=link)
        except Exception:
            # A provider may have accepted before its acknowledgement was lost.
            # No automatic retry and no exception details with sensitive payloads.
            raise DeliveryUnavailable('发送结果未确认，请稍后再试；没有自动重复发送。') from None

    def _email(self, contact, *, code, link):
        s = self.settings
        mail = EmailMessage()
        mail['From'] = s.contact_smtp_from
        mail['To'] = contact
        mail['Subject'] = '勿忘我 · 领取验证码' if code else '勿忘我 · 有一份留给你的内容'
        mail.set_content(f'领取验证码：{code}。5分钟内有效，请不要转发。若非本人操作，请忽略。' if code else
                         f'有人为你留下了一份内容。请打开以下链接，并通过本邮箱验证码领取：\n{link}\n\n链接本身不能直接读取内容。')
        context = ssl.create_default_context()
        if s.contact_smtp_tls == 'ssl':
            connection = smtplib.SMTP_SSL(s.contact_smtp_host, s.contact_smtp_port, timeout=12, context=context)
        else:
            connection = smtplib.SMTP(s.contact_smtp_host, s.contact_smtp_port, timeout=12)
        with connection as smtp:
            if s.contact_smtp_tls == 'starttls': smtp.starttls(context=context)
            smtp.login(s.contact_smtp_username, s.contact_smtp_password.get_secret_value())
            refused = smtp.send_message(mail)
            if refused: raise RuntimeError('recipient rejected')

    def _sms(self, contact, *, code, link):
        # Aliyun RPC SendSms, HTTPS POST form: no recipient/code in request URL.
        s = self.settings
        params = {
            'AccessKeyId': s.contact_sms_access_key_id, 'Action': 'SendSms', 'Format': 'JSON',
            'Version': '2017-05-25', 'RegionId': 'cn-hangzhou', 'SignatureMethod': 'HMAC-SHA1',
            'SignatureVersion': '1.0', 'SignatureNonce': uuid4().hex,
            'Timestamp': utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            'PhoneNumbers': contact.removeprefix('+86'), 'SignName': s.contact_sms_sign_name,
            'TemplateCode': s.contact_sms_code_template if code else s.contact_sms_notice_template,
            'TemplateParam': json.dumps({'code': code} if code else {'url': link}, ensure_ascii=False, separators=(',', ':')),
        }
        encode = lambda value: quote(str(value), safe='~')
        canonical = '&'.join(encode(k) + '=' + encode(v) for k, v in sorted(params.items()))
        signed = 'POST&%2F&' + encode(canonical)
        params['Signature'] = base64.b64encode(hmac.new(
            (s.contact_sms_access_key_secret.get_secret_value() + '&').encode(), signed.encode(), hashlib.sha1).digest()).decode()
        with httpx.Client(timeout=12, follow_redirects=False) as client:
            response = client.post('https://dysmsapi.aliyuncs.com/', data=params)
            if response.status_code != 200 or response.json().get('Code') != 'OK':
                raise RuntimeError('provider did not accept')
