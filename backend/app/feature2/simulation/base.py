"""
Abstract base class for Lagrangian particle simulation engines.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List
from ..schemas.simulation_schema import ParticleEnsemble
from ..data.base import EnvironmentalDataProvider


class ParticleSimulationEngine(ABC):
    """
    Abstract contract for running hydrodynamic particle tracking.
    """

    @abstractmethod
    def run(
        self,
        initial_ensemble: ParticleEnsemble,
        start_time: datetime,
        end_time: datetime,
        dt_seconds: int,
    ) -> List[ParticleEnsemble]:
        """
        Executes particle trajectory stepping from start_time to end_time.
        Returns time series snapshots of particle ensembles.
        """
        pass
