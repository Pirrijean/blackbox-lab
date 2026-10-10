from abc import ABC, abstractmethod
from blackbox_lab.core.contracts import InputObservation, OutputObservation

class TargetAdapter(ABC):
    @abstractmethod
    async def execute(self, observation: InputObservation) -> OutputObservation:
        """Ejecuta la consulta autorizada contra la caja negra de forma asíncrona."""
        pass

