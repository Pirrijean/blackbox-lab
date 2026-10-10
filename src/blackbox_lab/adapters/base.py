from abc import ABC, abstractmethod
from blackbox_lab.core.contracts import InputObservation, OutputObservation

class TargetAdapter(ABC):
    @abstractmethod
    def execute(self, observation: InputObservation) -> OutputObservation:
        """Ejecuta la consulta autorizada contra la caja negra."""
        pass
