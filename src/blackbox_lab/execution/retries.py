from pydantic import BaseModel
import time
from typing import Callable, Any

class RetryPolicy(BaseModel):
    max_retries: int = 3
    backoff_factor: float = 2.0
    base_delay_seconds: float = 1.0

def execute_with_retry(func: Callable, policy: RetryPolicy, *args, **kwargs) -> Any:
    delay = policy.base_delay_seconds
    for attempt in range(policy.max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == policy.max_retries:
                raise e
            time.sleep(delay)
            delay *= policy.backoff_factor
