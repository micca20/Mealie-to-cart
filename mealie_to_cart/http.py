from __future__ import annotations

from dataclasses import dataclass
import requests


@dataclass(frozen=True)
class HttpClient:
    base_url: str
    token: str
    timeout_s: float = 30.0

    def get(self, path: str, *, params: dict | None = None) -> requests.Response:
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        return requests.get(
            url,
            params=params,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
            timeout=self.timeout_s,
        )
