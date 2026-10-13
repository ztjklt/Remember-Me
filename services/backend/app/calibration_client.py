"""Private transport to AI Core's calibration worker."""

import httpx


class CalibrationUnavailable(RuntimeError):
    pass


class CalibrationClient:
    def __init__(self, url: str, timeout: float) -> None:
        self.url = url.rstrip("/") + "/calibrate"
        self.timeout = timeout

    def compare(self, question: str, locked_answer: str, human_answer: str) -> dict:
        try:
            response = httpx.post(self.url, json={"question": question,
                                                  "locked_answer": locked_answer,
                                                  "human_answer": human_answer},
                                  timeout=self.timeout, follow_redirects=False, trust_env=False)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise CalibrationUnavailable("校准暂时无法完成，可以稍后重试。") from exc
