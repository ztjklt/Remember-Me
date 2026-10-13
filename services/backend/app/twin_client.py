"""Backend's private transport to the evidence answer worker."""

import httpx


class TwinUnavailable(RuntimeError):
    retryable = True
    code = 'TWIN_UNAVAILABLE'


class TwinRejected(TwinUnavailable):
    retryable = False

    def __init__(self, code):
        self.code = code
        super().__init__('模型连接鉴权失败，请检查服务配置。' if code == 'AI_AUTH_FAILED' else
                         '模型回答未通过来源或格式校验，本次未保存答案。')


class TwinClient:
    def __init__(self, url: str, timeout: float) -> None:
        self.url = url.rstrip("/") + "/twin"
        self.timeout = timeout

    def express(self, answer, examples):
        try:
            response=httpx.post(self.url.removesuffix('/twin')+'/expression',
                json={'answer':answer,'examples':examples},timeout=110,follow_redirects=False,trust_env=False)
            response.raise_for_status(); data=response.json()
            if (not isinstance(data,dict) or set(data)!={'status','text','model_version','prompt_version'}
                or data['status'] not in {'available','rejected'} or not isinstance(data['text'],str)
                or len(data['text'])>500 or any(not isinstance(data[k],str) or not 0<len(data[k])<=128 for k in ('model_version','prompt_version'))
                or (data['status']=='rejected' and data['text'])):
                raise ValueError('Invalid expression')
            return data
        except (httpx.HTTPError,ValueError):
            return {'status':'unavailable','text':'','model_version':'','prompt_version':'expression-v1'}

    def answer(self, question: str, candidates: list[dict]) -> dict:
        try:
            response = httpx.post(self.url, json={"question": question, "candidates": candidates},
                                  timeout=self.timeout, follow_redirects=False, trust_env=False)
            if response.is_error:
                try:
                    body = response.json()
                    code = body.get('error_code') if isinstance(body, dict) else None
                except ValueError:
                    code = None
                if code in {'AI_SCHEMA_INVALID', 'EVIDENCE_INVALID', 'AI_AUTH_FAILED'}:
                    raise TwinRejected(code)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TwinUnavailable("Twin 模型暂时不可用，请稍后重试。") from exc
