"""
Internal data models for simulation states, particle ensembles, and environmental grid queries.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import numpy as np
from pydantic import BaseModel, Field


class ParticleState(BaseModel):
    """Lagrangian particle state in spacetime."""
    id: int
    latitude: float
    longitude: float
    timestamp: Optional[datetime] = None
    ensemble_member_id: int = 0
    age_seconds: float = 0.0
    mass_kg: float = 1.0
    is_active: bool = True
    beached: bool = False

    @property
    def particle_id(self) -> str:
        return f"p_{self.id:04d}"

    @property
    def active(self) -> bool:
        return self.is_active


class Particle(BaseModel):
    """Lagrangian particle model for forward transport tracking."""
    particle_id: str
    latitude: float
    longitude: float
    timestamp: datetime
    ensemble_member_id: int = 0
    active: bool = True
    age_seconds: float = 0.0
    mass_kg: float = 1.0


class Trajectory(BaseModel):
    """Time-indexed trajectory history for a single particle."""
    particle_id: str
    ensemble_member_id: int = 0
    states: List[ParticleState] = Field(default_factory=list)


class EnsembleStepStatistics(BaseModel):
    """Ensemble-derived spatial dispersion spread and uncertainty at a simulation step."""
    timestamp: datetime
    active_particle_count: int
    mean_latitude: float
    mean_longitude: float
    variance_east_m2: float
    variance_north_m2: float
    covariance_en_m2: float
    covariance_matrix_m2: List[List[float]] = Field(
        default_factory=list,
        description="2x2 spatial covariance matrix [[var_E, cov_EN], [cov_EN, var_N]] in local meters."
    )
    spread_radius_m: float = Field(
        default=0.0,
        description="Ensemble-derived dispersion spread radius in meters (sqrt(var_E + var_N))."
    )


class ForwardSimulationResult(BaseModel):
    """Structured result of a forward particle advection simulation."""
    start_time: datetime
    end_time: datetime
    timestep_seconds: int
    particle_count: int
    trajectories: List[Trajectory] = Field(default_factory=list)
    step_statistics: Optional[List[EnsembleStepStatistics]] = None


class EnsembleSimulationResult(BaseModel):
    """Structured result of a forward stochastic ensemble simulation."""
    start_time: datetime
    end_time: datetime
    timestep_seconds: int
    ensemble_size: int
    particles_per_member: int
    total_trajectories_count: int
    trajectories: List[Trajectory] = Field(default_factory=list)
    step_statistics: List[EnsembleStepStatistics] = Field(default_factory=list)


class ParticleEnsemble(BaseModel):
    """Ensemble collection of Lagrangian particles representing a slick."""
    spill_id: str
    timestamp: datetime
    particles: List[ParticleState] = Field(default_factory=list)

    def active_coordinates(self) -> List[tuple]:
        """Returns list of (lat, lon) coordinates for active non-beached particles."""
        return [(p.latitude, p.longitude) for p in self.particles if p.is_active and not p.beached]


class EnvironmentalQueryWindow(BaseModel):
    """Spacetime bounding window for environmental data interpolation."""
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    start_time: datetime
    end_time: datetime


class AdvectionVector(BaseModel):
    """Total combined surface advection velocity at a point."""
    u_total_ms: float = Field(..., description="Eastward velocity component in m/s.")
    v_total_ms: float = Field(..., description="Northward velocity component in m/s.")
    u_current_ms: float = Field(0.0, description="Ocean current eastward component.")
    v_current_ms: float = Field(0.0, description="Ocean current northward component.")
    u_wind_ms: float = Field(0.0, description="Surface wind eastward component.")
    v_wind_ms: float = Field(0.0, description="Surface wind northward component.")


class BackwardCandidateState(BaseModel):
    """Reconstructed candidate release state at a discrete historical release timestamp."""
    candidate_release_time: datetime
    backward_duration_hours: float
    reconstructed_centroid_latitude: float
    reconstructed_centroid_longitude: float
    active_particle_count: int
    total_particle_count: int
    spatial_spread_radius_m: float
    variance_east_m2: float
    variance_north_m2: float
    covariance_en_m2: float = 0.0
    reconstructed_particles: List[ParticleState] = Field(default_factory=list)


class BackwardSimulationResult(BaseModel):
    """Structured result of a backward / inverse Lagrangian particle reconstruction."""
    observation_time: datetime
    target_release_time: datetime
    backward_duration_seconds: float
    timestep_seconds: int
    particle_count: int
    active_particle_count: int
    reconstructed_centroid_latitude: float
    reconstructed_centroid_longitude: float
    spatial_spread_radius_m: float
    trajectories: List[Trajectory] = Field(default_factory=list)
    step_statistics: List[EnsembleStepStatistics] = Field(default_factory=list)


class BackwardCandidateEvaluationResult(BaseModel):
    """Collection of evaluated candidate release states across discrete historical search horizons."""
    observation_time: datetime
    max_backtrack_hours: float
    candidate_interval_hours: float
    candidate_count: int
    candidates: List[BackwardCandidateState] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
