"""Backend's private transport to the evidence answer worker."""

import httpx


class TwinUnavailable(RuntimeError):
    pass


class TwinClient:
    def __init__(self, url: str, timeout: float) -> None:
        self.url = url.rstrip("/") + "/twin"
        self.timeout = timeout

    def answer(self, question: str, candidates: list[dict]) -> dict:
        try:
            response = httpx.post(self.url, json={"question": question, "candidates": candidates},
                                  timeout=self.timeout, follow_redirects=False, trust_env=False)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TwinUnavailable("Twin 模型暂时不可用，请稍后重试。") from exc
