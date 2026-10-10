from abc import ABC, abstractmethod
from blackbox_lab.core.contracts import InputObservation, OutputObservation

class TargetAdapter(ABC):
    @abstractmethod
    async def execute(
        self, observation: InputObservation, *, request_id: str
    ) -> OutputObservation:
        """Execute one authorised request with a stable idempotency key.

        Remote adapters must forward ``request_id`` to a provider-supported
        idempotency mechanism.  If a provider cannot do that, a timeout is
        indeterminate and is never retried automatically.
        """
        pass

