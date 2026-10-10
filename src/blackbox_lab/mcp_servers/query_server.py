import asyncio
import ipaddress
import json
import os
import socket
from pathlib import Path

import httpx
from mcp.server import MCPServer

mcp = MCPServer("restricted-query")
CONFIG_PATH = os.environ.get("FRONTIER_CONFIG", "configs/demo.json")


def load_config() -> dict:
    path = Path(CONFIG_PATH)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def is_safe_target_host(hostname: str) -> bool:
    try:
        addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        for _family, _kind, _proto, _canonname, sockaddr in addresses:
            addr = ipaddress.ip_address(sockaddr[0].split("%", 1)[0])
            if (
                not addr.is_global
                or addr.is_multicast
                or addr.is_loopback
                or addr.is_private
                or addr.is_reserved
                or addr.is_link_local
            ):
                return False
        return True
    except Exception:
        return False


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

        from urllib.parse import urlsplit
        parsed_url = urlsplit(url)
        if parsed_url.scheme not in ("http", "https"):
            raise ValueError("Esquema de URL no permitido.")
        if not parsed_url.hostname or not is_safe_target_host(parsed_url.hostname):
            raise ValueError("Destino HTTP privado o no permitido por política de seguridad.")

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

            if len(resp.content) > 1_000_000:
                return json.dumps({"ok": False, "status": "blocked", "reason": "Respuesta excede el límite de 1MB"})

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
