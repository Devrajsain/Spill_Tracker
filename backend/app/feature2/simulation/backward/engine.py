"""
Backward / inverse Lagrangian particle trajectory reconstruction engine (Task 3C).
Reconstructs observed slick particle histories backward in time from observation timestamp T0:
  dx_back = -u_eff * dt [meters]
  dy_back = -v_eff * dt [meters]
where:
  u_eff = u_current + leeway * (u_wind * cos(theta) - v_wind * sin(theta))
  v_eff = v_current + leeway * (u_wind * sin(theta) + v_wind * cos(theta))

SCIENTIFIC PRINCIPLE:
This is an inverse advection approximation. Forward stochastic diffusion is NOT
time-reversible by simply changing the sign of dt. Stochastic diffusion is therefore
explicitly disabled during deterministic backward reconstruction.
"""

from datetime import datetime, timedelta
import math
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import numpy as np

from ...schemas.simulation_schema import (
    Particle,
    ParticleState,
    Trajectory,
    EnsembleStepStatistics,
    BackwardCandidateState,
    BackwardSimulationResult,
    BackwardCandidateEvaluationResult,
    ParticleEnsemble,
)
from ...schemas.input_schema import SlickDetectionInput, CentroidCoordinates
from ...data.base import EnvironmentalDataProvider, CurrentSample, WindSample
from ...data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from ...data.coord_utils import normalize_longitude
from ...data.time_utils import normalize_to_utc
from ...geo.coordinates import meters_to_lat_deg, meters_to_lon_deg, haversine_distance_km
from ...uncertainty.spatial_error import compute_ensemble_step_statistics
from ...config import Feature2Settings, default_settings
from ...exceptions import EnvironmentalCoverageError, OutOfDomainError, EnvironmentalDataUnavailableError
from ...logging_config import logger
from ..base import ParticleSimulationEngine
from ..particles import ParticleManager
from ..advection import AdvectionCalculator


class BackwardSimulationEngine(ParticleSimulationEngine):
    """
    CPU-based backward Lagrangian particle reconstruction engine.
    Solves inverse advection:
      x(t - dt) = x(t) - V(x, t) * dt
    moving particles in reverse time while querying historical environmental data
    at the particle's actual moving location and historical timestamp.
    """

    def __init__(
        self,
        currents_provider: EnvironmentalDataProvider,
        wind_provider: Optional[EnvironmentalDataProvider] = None,
        settings: Optional[Feature2Settings] = None,
    ):
        self.currents_provider = currents_provider
        self.wind_provider = wind_provider
        self.settings = settings or default_settings
        self.advection_calc = AdvectionCalculator(self.settings.windage)

    def simulate_backward(
        self,
        initial_particles: Union[List[Particle], ParticleEnsemble, SlickDetectionInput, SentinelObservationDomain],
        observation_time: Optional[Union[datetime, str]] = None,
        duration_seconds: float = 3600.0,
        dt_seconds: float = 600.0,
        windage_fraction: Optional[float] = None,
        query_domain: Optional[EnvironmentalQueryDomain] = None,
        step_callback: Optional[Callable[[Particle, float, float, datetime], None]] = None,
    ) -> BackwardSimulationResult:
        """
        Reconstructs particle trajectories backward in time from observation timestamp T0.

        Args:
            initial_particles: Observed slick particles or Feature 1 source at T0.
            observation_time: Observation timestamp T0. If None, inferred from particles.
            duration_seconds: Historical backtrack duration in seconds (>= 0).
            dt_seconds: Discrete reverse timestep in seconds (> 0).
            windage_fraction: Leeway factor (defaults to config windage leeway factor).
            query_domain: Optional governing domain for spatial/temporal validation.
            step_callback: Optional diagnostic hook invoked on each particle step.

        Returns:
            BackwardSimulationResult containing reverse trajectories and reconstructed origin state.
        """
        if dt_seconds <= 0:
            raise ValueError(f"Reverse timestep dt_seconds must be positive (> 0), got: {dt_seconds}")
        if duration_seconds < 0:
            raise ValueError(f"Backward duration_seconds must be non-negative (>= 0), got: {duration_seconds}")
        if self.currents_provider is None:
            raise ValueError("A valid historical ocean current provider is required for backward reconstruction.")

        # Resolve particles
        particles: List[Particle] = self._resolve_initial_particles(initial_particles)
        if not particles:
            raise ValueError("At least one initial particle is required for backward simulation.")

        # Determine observation time T0 (normalized UTC)
        if observation_time is not None:
            sim_t0 = normalize_to_utc(observation_time)
        else:
            sim_t0 = normalize_to_utc(particles[0].timestamp)

        for p in particles:
            p.timestamp = sim_t0

        effective_leeway = windage_fraction if windage_fraction is not None else self.settings.windage.leeway_factor
        deflection_rad = math.radians(self.settings.windage.deflection_angle_deg)
        cos_theta = math.cos(deflection_rad)
        sin_theta = math.sin(deflection_rad)

        num_steps = int(duration_seconds // dt_seconds)
        has_remainder = (duration_seconds % dt_seconds) > 1e-6
        remainder_dt = duration_seconds - (num_steps * dt_seconds)
        total_steps = num_steps + (1 if has_remainder else 0)

        # Initialize trajectory history starting at T0
        trajectories: Dict[str, List[ParticleState]] = {
            p.particle_id: [
                ParticleState(
                    id=idx,
                    latitude=p.latitude,
                    longitude=p.longitude,
                    timestamp=sim_t0,
                    ensemble_member_id=getattr(p, "ensemble_member_id", 0),
                    age_seconds=0.0,
                    mass_kg=p.mass_kg,
                    is_active=p.active,
                    beached=False
                )
            ]
            for idx, p in enumerate(particles)
        }

        step_statistics_list: List[EnsembleStepStatistics] = []
        initial_states = [trajectories[p.particle_id][0] for p in particles]
        step_statistics_list.append(compute_ensemble_step_statistics(sim_t0, initial_states))

        current_reverse_time = sim_t0

        # Step backward in reverse time: T0 -> T0 - dt -> T0 - 2dt -> ...
        for step_idx in range(total_steps):
            step_dt = remainder_dt if (step_idx == num_steps and has_remainder) else dt_seconds
            # Reverse-time clock progression: subtract dt
            next_reverse_time = current_reverse_time - timedelta(seconds=step_dt)

            step_states_snapshot: List[ParticleState] = []

            for idx, p in enumerate(particles):
                if not p.active:
                    # Carry forward deactivated terminal state
                    step_states_snapshot.append(
                        ParticleState(
                            id=idx,
                            latitude=p.latitude,
                            longitude=p.longitude,
                            timestamp=next_reverse_time,
                            ensemble_member_id=getattr(p, "ensemble_member_id", 0),
                            age_seconds=p.age_seconds,
                            mass_kg=p.mass_kg,
                            is_active=False,
                            beached=False
                        )
                    )
                    continue

                # 1. Query historical current velocity at particle's actual location and reverse time
                try:
                    curr_sample = self.currents_provider.get_current(
                        latitude=p.latitude,
                        longitude=p.longitude,
                        timestamp=current_reverse_time
                    )
                    u_curr = curr_sample.u
                    v_curr = curr_sample.v
                except (EnvironmentalCoverageError, OutOfDomainError, EnvironmentalDataUnavailableError) as err:
                    logger.warning(
                        f"Particle {p.particle_id} out of historical current data coverage at "
                        f"({p.latitude:.4f}, {p.longitude:.4f}, {current_reverse_time.isoformat()}): {err}. "
                        "Deactivating particle."
                    )
                    p.active = False
                    deactivated_state = ParticleState(
                        id=idx,
                        latitude=p.latitude,
                        longitude=p.longitude,
                        timestamp=next_reverse_time,
                        ensemble_member_id=getattr(p, "ensemble_member_id", 0),
                        age_seconds=p.age_seconds + step_dt,
                        mass_kg=p.mass_kg,
                        is_active=False,
                        beached=False
                    )
                    trajectories[p.particle_id].append(deactivated_state)
                    step_states_snapshot.append(deactivated_state)
                    continue

                # 2. Query historical wind velocity if configured
                u_wind = 0.0
                v_wind = 0.0
                if self.wind_provider is not None and effective_leeway > 0.0:
                    try:
                        wind_sample = self.wind_provider.get_wind(
                            latitude=p.latitude,
                            longitude=p.longitude,
                            timestamp=current_reverse_time
                        )
                        u_wind = wind_sample.u
                        v_wind = wind_sample.v
                    except (EnvironmentalCoverageError, OutOfDomainError, EnvironmentalDataUnavailableError) as err:
                        logger.warning(
                            f"Particle {p.particle_id} out of historical wind data coverage at "
                            f"({p.latitude:.4f}, {p.longitude:.4f}, {current_reverse_time.isoformat()}): {err}. "
                            "Deactivating particle."
                        )
                        p.active = False
                        deactivated_state = ParticleState(
                            id=idx,
                            latitude=p.latitude,
                            longitude=p.longitude,
                            timestamp=next_reverse_time,
                            ensemble_member_id=getattr(p, "ensemble_member_id", 0),
                            age_seconds=p.age_seconds + step_dt,
                            mass_kg=p.mass_kg,
                            is_active=False,
                            beached=False
                        )
                        trajectories[p.particle_id].append(deactivated_state)
                        step_states_snapshot.append(deactivated_state)
                        continue

                # 3. Combine deterministic effective velocity with windage
                u_wind_eff = effective_leeway * (u_wind * cos_theta - v_wind * sin_theta)
                v_wind_eff = effective_leeway * (u_wind * sin_theta + v_wind * cos_theta)
                u_eff = u_curr + u_wind_eff
                v_eff = v_curr + v_wind_eff

                if step_callback is not None:
                    step_callback(p, u_eff, v_eff, current_reverse_time)

                # 4. Backward displacement: move opposite to velocity vector
                dx_back_meters = -u_eff * step_dt
                dy_back_meters = -v_eff * step_dt

                # 5. Geodesic coordinate conversion
                dlat_deg = meters_to_lat_deg(dy_back_meters)
                dlon_deg = meters_to_lon_deg(dx_back_meters, at_latitude=p.latitude)

                new_lat = p.latitude + dlat_deg
                new_lon = normalize_longitude(p.longitude + dlon_deg)

                if new_lat > 90.0:
                    new_lat = 90.0
                elif new_lat < -90.0:
                    new_lat = -90.0

                p.latitude = new_lat
                p.longitude = new_lon
                p.timestamp = next_reverse_time
                p.age_seconds += step_dt

                state = ParticleState(
                    id=idx,
                    latitude=new_lat,
                    longitude=new_lon,
                    timestamp=next_reverse_time,
                    ensemble_member_id=getattr(p, "ensemble_member_id", 0),
                    age_seconds=p.age_seconds,
                    mass_kg=p.mass_kg,
                    is_active=True,
                    beached=False
                )
                trajectories[p.particle_id].append(state)
                step_states_snapshot.append(state)

            current_reverse_time = next_reverse_time
            step_statistics_list.append(
                compute_ensemble_step_statistics(current_reverse_time, step_states_snapshot)
            )

        result_trajectories = [
            Trajectory(
                particle_id=p_id,
                ensemble_member_id=states[0].ensemble_member_id if states else 0,
                states=states
            )
            for p_id, states in trajectories.items()
        ]

        target_release_time = sim_t0 - timedelta(seconds=duration_seconds)
        final_stats = step_statistics_list[-1]
        active_count = sum(1 for p in particles if p.active)

        return BackwardSimulationResult(
            observation_time=sim_t0,
            target_release_time=target_release_time,
            backward_duration_seconds=duration_seconds,
            timestep_seconds=int(dt_seconds),
            particle_count=len(particles),
            active_particle_count=active_count,
            reconstructed_centroid_latitude=final_stats.mean_latitude,
            reconstructed_centroid_longitude=final_stats.mean_longitude,
            spatial_spread_radius_m=final_stats.spread_radius_m,
            trajectories=result_trajectories,
            step_statistics=step_statistics_list
        )

    def evaluate_backward_candidates(
        self,
        source: Union[List[Particle], ParticleEnsemble, SlickDetectionInput, SentinelObservationDomain],
        observation_time: Optional[Union[datetime, str]] = None,
        max_backtrack_hours: Optional[float] = None,
        candidate_interval_hours: Optional[float] = None,
        dt_seconds: float = 600.0,
        particles_per_slick: Optional[int] = None,
        windage_fraction: Optional[float] = None,
        query_domain: Optional[EnvironmentalQueryDomain] = None,
    ) -> BackwardCandidateEvaluationResult:
        """
        Evaluates candidate release states across discrete historical release intervals
        [T0 - dt_interval, T0 - 2*dt_interval, ..., T0 - max_backtrack].

        Args:
            source: SlickDetectionInput, SentinelObservationDomain, or Particle set.
            observation_time: Observation timestamp T0.
            max_backtrack_hours: Maximum historical search window in hours (default from config).
            candidate_interval_hours: Interval between candidate release times (default from config).
            dt_seconds: Integration timestep for advection stepping.
            particles_per_slick: Number of particles to seed if source is a polygon.
            windage_fraction: Leeway factor.
            query_domain: Environmental domain for spatial bounding.

        Returns:
            BackwardCandidateEvaluationResult containing evaluated candidate states.
        """
        horizon_hours = (
            max_backtrack_hours if max_backtrack_hours is not None
            else self.settings.backward.max_backtrack_hours
        )
        interval_hours = (
            candidate_interval_hours if candidate_interval_hours is not None
            else self.settings.backward.candidate_time_step_hours
        )

        candidate_times = generate_candidate_release_times(
            observation_time=observation_time or datetime.now(timezone.utc),
            horizon_hours=horizon_hours,
            interval_hours=interval_hours
        )

        # Run continuous backward simulation to the maximum horizon
        max_duration_seconds = horizon_hours * 3600.0
        full_result = self.simulate_backward(
            initial_particles=source,
            observation_time=observation_time,
            duration_seconds=max_duration_seconds,
            dt_seconds=dt_seconds,
            windage_fraction=windage_fraction,
            query_domain=query_domain
        )

        # Extract candidate states corresponding to discrete candidate release times
        candidate_states: List[BackwardCandidateState] = []

        for cand_time in candidate_times:
            # Find the closest step in step_statistics
            closest_stat = min(
                full_result.step_statistics,
                key=lambda s: abs((s.timestamp - cand_time).total_seconds())
            )

            # Gather particle states at this closest timestamp
            particles_at_cand: List[ParticleState] = []
            for traj in full_result.trajectories:
                closest_state = min(
                    traj.states,
                    key=lambda st: abs((st.timestamp - cand_time).total_seconds())
                )
                particles_at_cand.append(closest_state)

            duration_h = (full_result.observation_time - cand_time).total_seconds() / 3600.0
            candidate_states.append(
                BackwardCandidateState(
                    candidate_release_time=cand_time,
                    backward_duration_hours=round(duration_h, 3),
                    reconstructed_centroid_latitude=closest_stat.mean_latitude,
                    reconstructed_centroid_longitude=closest_stat.mean_longitude,
                    active_particle_count=closest_stat.active_particle_count,
                    total_particle_count=full_result.particle_count,
                    spatial_spread_radius_m=closest_stat.spread_radius_m,
                    variance_east_m2=closest_stat.variance_east_m2,
                    variance_north_m2=closest_stat.variance_north_m2,
                    covariance_en_m2=closest_stat.covariance_en_m2,
                    reconstructed_particles=particles_at_cand
                )
            )

        return BackwardCandidateEvaluationResult(
            observation_time=full_result.observation_time,
            max_backtrack_hours=horizon_hours,
            candidate_interval_hours=interval_hours,
            candidate_count=len(candidate_states),
            candidates=candidate_states,
            metadata={
                "timestep_seconds": dt_seconds,
                "total_particle_count": full_result.particle_count,
                "current_provider": self.currents_provider.provider_name if self.currents_provider else None,
                "wind_provider": self.wind_provider.provider_name if self.wind_provider else None,
            }
        )

    def _resolve_initial_particles(
        self,
        initial_particles: Union[List[Particle], ParticleEnsemble, SlickDetectionInput, SentinelObservationDomain]
    ) -> List[Particle]:
        """Resolves particles from various supported input representations."""
        if isinstance(initial_particles, list):
            resolved = []
            for item in initial_particles:
                if isinstance(item, Particle):
                    resolved.append(item.model_copy())
                elif isinstance(item, ParticleState):
                    resolved.append(
                        Particle(
                            particle_id=item.particle_id,
                            latitude=item.latitude,
                            longitude=item.longitude,
                            timestamp=item.timestamp or datetime.now(timezone.utc),
                            ensemble_member_id=item.ensemble_member_id,
                            active=item.is_active,
                            age_seconds=item.age_seconds,
                            mass_kg=item.mass_kg
                        )
                    )
                elif isinstance(item, dict):
                    resolved.append(Particle(**item))
            return resolved

        if isinstance(initial_particles, ParticleEnsemble):
            return [
                Particle(
                    particle_id=f"p_{p.id:04d}",
                    latitude=p.latitude,
                    longitude=p.longitude,
                    timestamp=initial_particles.timestamp,
                    ensemble_member_id=getattr(p, "ensemble_member_id", 0),
                    active=p.is_active,
                    age_seconds=p.age_seconds,
                    mass_kg=p.mass_kg
                )
                for p in initial_particles.particles
            ]

        if isinstance(initial_particles, (SlickDetectionInput, SentinelObservationDomain)):
            return ParticleManager.seed_particles(
                source=initial_particles,
                num_particles=self.settings.backward.particles_per_slick,
                random_seed=self.settings.random_seed
            )

        raise ValueError(f"Cannot resolve particles from source of type: {type(initial_particles)}")

    def run(
        self,
        initial_ensemble: ParticleEnsemble,
        start_time: datetime,
        end_time: datetime,
        dt_seconds: int = 600,
    ) -> List[ParticleEnsemble]:
        """
        Executes particle stepping satisfying ParticleSimulationEngine abstract contract.
        Returns time series snapshots of ParticleEnsemble objects in chronological reverse order.
        """
        duration = max((normalize_to_utc(start_time) - normalize_to_utc(end_time)).total_seconds(), 0.0)
        result = self.simulate_backward(
            initial_particles=initial_ensemble,
            observation_time=start_time,
            duration_seconds=duration,
            dt_seconds=float(dt_seconds)
        )

        if not result.trajectories or not result.trajectories[0].states:
            return [initial_ensemble]

        num_snapshots = len(result.trajectories[0].states)
        snapshots: List[ParticleEnsemble] = []

        for step_idx in range(num_snapshots):
            step_particles = [
                traj.states[step_idx]
                for traj in result.trajectories
                if step_idx < len(traj.states)
            ]
            snap_time = step_particles[0].timestamp if step_particles else start_time
            snapshots.append(
                ParticleEnsemble(
                    spill_id=initial_ensemble.spill_id,
                    timestamp=snap_time,
                    particles=step_particles
                )
            )

        return snapshots


def generate_candidate_release_times(
    observation_time: Union[datetime, str],
    horizon_hours: float = 72.0,
    interval_hours: float = 3.0,
) -> List[datetime]:
    """
    Generates discrete candidate release timestamps [T0 - interval, T0 - 2*interval, ..., T0 - horizon]
    strictly in timezone-aware UTC.
    """
    if horizon_hours <= 0:
        raise ValueError(f"horizon_hours must be positive (> 0), got: {horizon_hours}")
    if interval_hours <= 0:
        raise ValueError(f"interval_hours must be positive (> 0), got: {interval_hours}")

    t0 = normalize_to_utc(observation_time)
    num_candidates = int(horizon_hours // interval_hours)
    candidate_times: List[datetime] = []

    for k in range(1, num_candidates + 1):
        cand_time = t0 - timedelta(hours=k * interval_hours)
        candidate_times.append(cand_time)

    return candidate_times


def simulate_backward(
    initial_particles: Union[List[Particle], ParticleEnsemble, SlickDetectionInput, SentinelObservationDomain],
    observation_time: Optional[Union[datetime, str]] = None,
    duration_seconds: float = 3600.0,
    dt_seconds: float = 600.0,
    current_provider: Optional[EnvironmentalDataProvider] = None,
    wind_provider: Optional[EnvironmentalDataProvider] = None,
    windage_fraction: Optional[float] = None,
    config: Optional[Feature2Settings] = None,
    query_domain: Optional[EnvironmentalQueryDomain] = None,
    step_callback: Optional[Callable[[Particle, float, float, datetime], None]] = None,
) -> BackwardSimulationResult:
    """
    Convenience functional interface for backward Lagrangian particle reconstruction.
    """
    settings = config or default_settings
    if current_provider is None:
        raise ValueError("current_provider is required for simulate_backward.")

    engine = BackwardSimulationEngine(
        currents_provider=current_provider,
        wind_provider=wind_provider,
        settings=settings
    )

    return engine.simulate_backward(
        initial_particles=initial_particles,
        observation_time=observation_time,
        duration_seconds=duration_seconds,
        dt_seconds=dt_seconds,
        windage_fraction=windage_fraction,
        query_domain=query_domain,
        step_callback=step_callback
    )


def evaluate_backward_candidates(
    source: Union[List[Particle], ParticleEnsemble, SlickDetectionInput, SentinelObservationDomain],
    observation_time: Optional[Union[datetime, str]] = None,
    max_backtrack_hours: Optional[float] = None,
    candidate_interval_hours: Optional[float] = None,
    dt_seconds: float = 600.0,
    current_provider: Optional[EnvironmentalDataProvider] = None,
    wind_provider: Optional[EnvironmentalDataProvider] = None,
    windage_fraction: Optional[float] = None,
    config: Optional[Feature2Settings] = None,
    query_domain: Optional[EnvironmentalQueryDomain] = None,
) -> BackwardCandidateEvaluationResult:
    """
    Convenience functional interface for evaluating backward candidate release states.
    """
    settings = config or default_settings
    if current_provider is None:
        raise ValueError("current_provider is required for evaluate_backward_candidates.")

    engine = BackwardSimulationEngine(
        currents_provider=current_provider,
        wind_provider=wind_provider,
        settings=settings
    )

    return engine.evaluate_backward_candidates(
        source=source,
        observation_time=observation_time,
        max_backtrack_hours=max_backtrack_hours,
        candidate_interval_hours=candidate_interval_hours,
        dt_seconds=dt_seconds,
        windage_fraction=windage_fraction,
        query_domain=query_domain
    )
