import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class TransientReadError(Exception):
    """Fallo transitorio clasificado por un adaptador de lectura."""


class RetryPolicy(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        revalidate_instances="always",
    )

    max_retries: int = Field(2, ge=0, le=5, strict=True)
    base_delay_seconds: float = Field(0.5, ge=0, le=10, strict=True)
    backoff_factor: float = Field(2.0, ge=1, le=3, strict=True)
    max_delay_seconds: float = Field(10.0, ge=0, le=30, strict=True)
    attempt_timeout_seconds: float = Field(10.0, gt=0, le=60, strict=True)
    total_timeout_seconds: float = Field(60.0, gt=0, le=300, strict=True)


async def execute_with_retry(
    func: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    *,
    safe_to_repeat: bool = False,
) -> T:
    if type(safe_to_repeat) is not bool:
        raise ValueError("safe_to_repeat debe ser un booleano real.")

    if not isinstance(policy, RetryPolicy):
        raise ValueError("Política de reintentos inválida.")

    policy = RetryPolicy.model_validate(policy.model_dump())

    async with asyncio.timeout(policy.total_timeout_seconds):
        for attempt in range(policy.max_retries + 1):
            try:
                async with asyncio.timeout(policy.attempt_timeout_seconds):
                    return await func()
            except (TransientReadError, TimeoutError):
                if not safe_to_repeat or attempt == policy.max_retries:
                    raise

                delay = min(
                    policy.max_delay_seconds,
                    policy.base_delay_seconds
                    * (policy.backoff_factor ** attempt),
                )
                await asyncio.sleep(delay)

    raise RuntimeError("Estado de reintentos inesperado.")
