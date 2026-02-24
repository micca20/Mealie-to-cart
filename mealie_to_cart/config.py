from __future__ import annotations

import os
import json
from dataclasses import dataclass
from urllib.request import Request, urlopen
from urllib.parse import urlencode


REQUIRED_KEYS = [
    "MEALIE_URL",
    "MEALIE_API_KEY",
    "WALMART_EMAIL",
    "WALMART_PASSWORD",
    "BROWSERLESS_URL",
    "BROWSERLESS_TOKEN",
]

# Infisical connection (read from env vars set in compose)
INFISICAL_URL = os.environ.get("INFISICAL_URL", "http://192.168.1.220:8089")
INFISICAL_CLIENT_ID = os.environ.get("INFISICAL_CLIENT_ID", "")
INFISICAL_CLIENT_SECRET = os.environ.get("INFISICAL_CLIENT_SECRET", "")
INFISICAL_PROJECT_ID = os.environ.get("INFISICAL_PROJECT_ID", "340a0095-6c0d-4114-b19a-5b2eb4d60d30")


@dataclass(frozen=True)
class Config:
    mealie_url: str
    mealie_api_key: str
    walmart_email: str
    walmart_password: str
    browserless_url: str
    browserless_token: str
    mealie_list_name: str = "Walmart"

    @staticmethod
    def load_from_infisical(*, env: str = "dev") -> "Config":
        token = _infisical_login()
        secrets = _infisical_list_secrets(token, env=env)

        values: dict[str, str] = {}
        for k in REQUIRED_KEYS:
            if k not in secrets:
                raise RuntimeError(f"Missing Infisical secret: {k}")
            val = secrets[k]
            if not val or val.strip() in {"PLACEHOLDER", "MASKED", ""}:
                raise RuntimeError(f"Infisical secret {k} is still a placeholder")
            values[k] = val

        return Config(
            mealie_url=values["MEALIE_URL"].rstrip("/"),
            mealie_api_key=values["MEALIE_API_KEY"],
            walmart_email=values["WALMART_EMAIL"],
            walmart_password=values["WALMART_PASSWORD"],
            browserless_url=values["BROWSERLESS_URL"].rstrip("/"),
            browserless_token=values["BROWSERLESS_TOKEN"],
        )


def _infisical_login() -> str:
    """Get an access token via Universal Auth."""
    url = f"{INFISICAL_URL}/api/v1/auth/universal-auth/login"
    body = json.dumps({
        "clientId": INFISICAL_CLIENT_ID,
        "clientSecret": INFISICAL_CLIENT_SECRET,
    }).encode()
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data["accessToken"]


def _infisical_list_secrets(token: str, *, env: str = "dev") -> dict[str, str]:
    """List all secrets from Infisical for the given environment."""
    params = urlencode({
        "projectId": INFISICAL_PROJECT_ID,
        "environment": env,
        "secretPath": "/",
    })
    url = f"{INFISICAL_URL}/api/v4/secrets?{params}"
    req = Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    secrets: dict[str, str] = {}
    for s in data.get("secrets", []):
        secrets[s["secretKey"]] = s["secretValue"]
    return secrets
