import asyncio
import json
import os
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("restricted-query")
CONFIG_PATH = os.environ.get("FRONTIER_CONFIG", "configs/demo.json")


def load_config() -> dict:
    path = Path(CONFIG_PATH)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@mcp.tool()
async def query(payload_json: str) -> str:
    try:
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise ValueError("La entrada debe ser un objeto JSON.")

        config = load_config()
        target = config.get("target", {"kind": "simulator"})

        if target.get("kind") == "simulator":
            values = list(payload.values())
            total = sum(float(v) ** 2 for v in values if isinstance(v, (int, float)))
            return json.dumps({
                "ok": True,
                "response": {"value": total, "score": 1.0 / (1.0 + total)},
                "cost_usd": 0.0,
            })

        # Target HTTP
        url = target.get("url")
        if not url:
            raise ValueError("URL de destino HTTP no configurada.")

        method = target.get("method", "POST")
        timeout_s = float(target.get("timeout_seconds", 10.0))

        headers = {}
        secret_env = target.get("secret_env")
        secret_val = os.environ.get(secret_env) if secret_env else None
        if secret_val:
            headers["Authorization"] = f"Bearer {secret_val}"

        async with httpx.AsyncClient(
            timeout=timeout_s,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            if method == "GET":
                resp = await client.get(url, params=payload, headers=headers)
            else:
                resp = await client.post(url, json=payload, headers=headers)

            if resp.status_code == 429 or resp.status_code >= 500:
                return json.dumps({"ok": False, "status": "transient"})

            if 300 <= resp.status_code < 400:
                return json.dumps({"ok": False, "status": "blocked", "reason": "Redirección no autorizada"})

            resp.raise_for_status()
            data = resp.json()

            if secret_val and secret_val in resp.text:
                return json.dumps({"ok": False, "status": "blocked", "reason": "Fuga de secreto detectada"})

            return json.dumps({
                "ok": True,
                "response": data,
                "cost_usd": target.get("maximum_call_usd", 0.0),
            })

    except Exception as exc:
        return json.dumps({
            "ok": False,
            "status": "failure",
            "error_type": type(exc).__name__,
        })


if __name__ == "__main__":
    mcp.run(transport="stdio")
