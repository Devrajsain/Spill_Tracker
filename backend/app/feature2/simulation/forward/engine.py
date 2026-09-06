"""
Forward Lagrangian particle advection & stochastic diffusion simulation engine (Task 3A & Task 3B).
Advances particles forward in time according to:
  1. Hydrodynamic ocean currents and surface windage:
     dx_adv = u_eff * dt, dy_adv = v_eff * dt
  2. Horizontal isotropic Fickian diffusion:
     sigma = sqrt(2 * Kh * dt)
     dE ~ Normal(0, sigma) [meters]
     dN ~ Normal(0, sigma) [meters]
  3. Total local horizontal displacement:
     dx_total = dx_adv + dE [meters]
     dy_total = dy_adv + dN [meters]
  4. Exact WGS84 geodesic conversion, strict out-of-coverage handling,
     and reproducible ensemble simulations with local metric spatial covariance.
"""

from datetime import datetime, timedelta
import math
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import numpy as np

from ...schemas.simulation_schema import (
    Particle,
    ParticleState,
    Trajectory,
    ForwardSimulationResult,
    EnsembleStepStatistics,
    EnsembleSimulationResult,
    ParticleEnsemble,
    AdvectionVector,
)
from ...schemas.input_schema import SlickDetectionInput
from ...data.base import EnvironmentalDataProvider, CurrentSample, WindSample, VectorFieldSample
from ...data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from ...data.coord_utils import normalize_longitude
from ...data.time_utils import normalize_to_utc
from ...geo.coordinates import meters_to_lat_deg, meters_to_lon_deg
from ...uncertainty.spatial_error import compute_ensemble_step_statistics
from ...config import Feature2Settings, default_settings
from ...exceptions import EnvironmentalCoverageError, OutOfDomainError, EnvironmentalDataUnavailableError
from ...logging_config import logger
from ..base import ParticleSimulationEngine
from ..particles import ParticleManager
from ..advection import AdvectionCalculator
from ..diffusion import TurbulentDiffusion


class ForwardSimulationEngine(ParticleSimulationEngine):
    """
    CPU-based forward Lagrangian particle transport engine with horizontal stochastic diffusion.
    Solves:
      total_east  = (u_current + leeway * u_wind_eff) * dt + dE
      total_north = (v_current + leeway * v_wind_eff) * dt + dN
    where dE, dN ~ Normal(0, sqrt(2 * Kh * dt)) in meters.
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
        self.diffusion_calc = TurbulentDiffusion(self.settings.diffusion)

    def simulate_forward(
        self,
        initial_particles: Union[List[Particle], ParticleEnsemble, SlickDetectionInput, SentinelObservationDomain],
        start_time: Optional[Union[datetime, str]] = None,
        duration_seconds: float = 3600.0,
        dt_seconds: float = 600.0,
        windage_fraction: Optional[float] = None,
        diffusion_enabled: Optional[bool] = False,
        diffusion_coefficient_m2_s: Optional[float] = None,
        random_seed: Optional[int] = None,
        query_domain: Optional[EnvironmentalQueryDomain] = None,
        step_callback: Optional[Callable[[Particle, float, float, datetime], None]] = None,
    ) -> ForwardSimulationResult:
        """
        Executes forward Lagrangian advection with optional stochastic horizontal diffusion.

        Args:
            initial_particles: Particles, ParticleEnsemble, or Feature 1 source to seed from.
            start_time: Initial simulation time T0. If None, derived from particles' timestamp.
            duration_seconds: Total simulation duration in seconds (must be >= 0).
            dt_seconds: Forward timestep in seconds (must be > 0).
            windage_fraction: Leeway multiplier (defaults to config windage leeway factor).
            diffusion_enabled: Whether stochastic diffusion is enabled (defaults to False for deterministic advection).
            diffusion_coefficient_m2_s: Horizontal diffusivity Kh in m^2/s (defaults to config).
            random_seed: Explicit seed for reproducible diffusion increments.
            query_domain: Optional governing domain for strict spatial/temporal validation.
            step_callback: Optional diagnostic hook invoked on each particle velocity query.

        Returns:
            ForwardSimulationResult containing time-indexed trajectories and step dispersion statistics.
        """
        # Validate numerical inputs
        if dt_seconds <= 0:
            raise ValueError(f"Simulation timestep dt_seconds must be positive (> 0), got: {dt_seconds}")
        if duration_seconds < 0:
            raise ValueError(f"Simulation duration_seconds must be non-negative (>= 0), got: {duration_seconds}")
        if self.currents_provider is None:
            raise ValueError("A valid ocean current provider is required for forward simulation.")

        # Determine diffusion parameters
        eff_diffusion_enabled = bool(diffusion_enabled)
        eff_kh = (
            diffusion_coefficient_m2_s if diffusion_coefficient_m2_s is not None
            else self.settings.diffusion.horizontal_diffusivity_m2_s
        )
        if eff_kh < 0.0:
            raise ValueError(f"diffusion_coefficient_m2_s must be non-negative (>= 0), got: {eff_kh}")

        # Initialize explicit local RNG for diffusion
        if random_seed is not None:
            diff_rng = np.random.Generator(np.random.PCG64(random_seed))
        elif self.settings.diffusion.random_seed is not None:
            diff_rng = np.random.Generator(np.random.PCG64(self.settings.diffusion.random_seed))
        else:
            diff_rng = np.random.default_rng()

        # Resolve initial particles
        particles: List[Particle] = self._resolve_initial_particles(initial_particles)
        if not particles:
            raise ValueError("At least one initial particle is required for forward simulation.")

        # Determine start time T0
        if start_time is not None:
            sim_t0 = normalize_to_utc(start_time)
        else:
            sim_t0 = normalize_to_utc(particles[0].timestamp)

        for p in particles:
            p.timestamp = sim_t0

        # Windage leeway parameters
        effective_leeway = windage_fraction if windage_fraction is not None else self.settings.windage.leeway_factor
        deflection_rad = math.radians(self.settings.windage.deflection_angle_deg)
        cos_theta = math.cos(deflection_rad)
        sin_theta = math.sin(deflection_rad)

        num_steps = int(duration_seconds // dt_seconds)
        has_remainder = (duration_seconds % dt_seconds) > 1e-6
        remainder_dt = duration_seconds - (num_steps * dt_seconds)

        # Initialize trajectories with initial state at T0
        trajectories: Dict[str, List[ParticleState]] = {
            p.particle_id: [
                ParticleState(
                    id=idx,
                    latitude=p.latitude,
                    longitude=p.longitude,
                    timestamp=sim_t0,
                    ensemble_member_id=p.ensemble_member_id,
                    age_seconds=0.0,
                    mass_kg=p.mass_kg,
                    is_active=p.active,
                    beached=False
                )
            ]
            for idx, p in enumerate(particles)
        }

        # Step-by-step forward advection + diffusion
        total_steps = num_steps + (1 if has_remainder else 0)
        current_step_time = sim_t0

        step_statistics_list: List[EnsembleStepStatistics] = []
        # Initial step statistics at T0
        initial_states = [trajectories[p.particle_id][0] for p in particles]
        step_statistics_list.append(compute_ensemble_step_statistics(sim_t0, initial_states))

        for step_idx in range(total_steps):
            step_dt = remainder_dt if (step_idx == num_steps and has_remainder) else dt_seconds
            next_step_time = current_step_time + timedelta(seconds=step_dt)

            # Standard deviation for horizontal diffusion: sigma = sqrt(2 * Kh * dt)
            if eff_diffusion_enabled and eff_kh > 0.0 and step_dt > 0.0:
                diff_sigma = math.sqrt(2.0 * eff_kh * step_dt)
            else:
                diff_sigma = 0.0

            step_states_snapshot: List[ParticleState] = []

            for idx, p in enumerate(particles):
                if not p.active:
                    # Carry forward deactivated terminal state
                    step_states_snapshot.append(
                        ParticleState(
                            id=idx,
                            latitude=p.latitude,
                            longitude=p.longitude,
                            timestamp=next_step_time,
                            ensemble_member_id=p.ensemble_member_id,
                            age_seconds=p.age_seconds,
                            mass_kg=p.mass_kg,
                            is_active=False,
                            beached=False
                        )
                    )
                    continue

                # 1. Query environmental current velocity at particle's spacetime location
                try:
                    curr_sample = self.currents_provider.get_current(
                        latitude=p.latitude,
                        longitude=p.longitude,
                        timestamp=current_step_time
                    )
                    u_curr = curr_sample.u
                    v_curr = curr_sample.v
                except (EnvironmentalCoverageError, OutOfDomainError, EnvironmentalDataUnavailableError) as err:
                    logger.warning(
                        f"Particle {p.particle_id} out of current data coverage at "
                        f"({p.latitude:.4f}, {p.longitude:.4f}, {current_step_time.isoformat()}): {err}. "
                        "Deactivating particle."
                    )
                    p.active = False
                    deactivated_state = ParticleState(
                        id=idx,
                        latitude=p.latitude,
                        longitude=p.longitude,
                        timestamp=next_step_time,
                        ensemble_member_id=p.ensemble_member_id,
                        age_seconds=p.age_seconds + step_dt,
                        mass_kg=p.mass_kg,
                        is_active=False,
                        beached=False
                    )
                    trajectories[p.particle_id].append(deactivated_state)
                    step_states_snapshot.append(deactivated_state)
                    continue

                # 2. Query environmental wind velocity if wind provider and windage are configured
                u_wind = 0.0
                v_wind = 0.0
                if self.wind_provider is not None and effective_leeway > 0.0:
                    try:
                        wind_sample = self.wind_provider.get_wind(
                            latitude=p.latitude,
                            longitude=p.longitude,
                            timestamp=current_step_time
                        )
                        u_wind = wind_sample.u
                        v_wind = wind_sample.v
                    except (EnvironmentalCoverageError, OutOfDomainError, EnvironmentalDataUnavailableError) as err:
                        logger.warning(
                            f"Particle {p.particle_id} out of wind data coverage at "
                            f"({p.latitude:.4f}, {p.longitude:.4f}, {current_step_time.isoformat()}): {err}. "
                            "Deactivating particle."
                        )
                        p.active = False
                        deactivated_state = ParticleState(
                            id=idx,
                            latitude=p.latitude,
                            longitude=p.longitude,
                            timestamp=next_step_time,
                            ensemble_member_id=p.ensemble_member_id,
                            age_seconds=p.age_seconds + step_dt,
                            mass_kg=p.mass_kg,
                            is_active=False,
                            beached=False
                        )
                        trajectories[p.particle_id].append(deactivated_state)
                        step_states_snapshot.append(deactivated_state)
                        continue

                # 3. Combine effective deterministic velocity with windage
                u_wind_eff = effective_leeway * (u_wind * cos_theta - v_wind * sin_theta)
                v_wind_eff = effective_leeway * (u_wind * sin_theta + v_wind * cos_theta)
                u_eff = u_curr + u_wind_eff
                v_eff = v_curr + v_wind_eff

                if step_callback is not None:
                    step_callback(p, u_eff, v_eff, current_step_time)

                # 4. Deterministic displacement in meters
                dx_adv_meters = u_eff * step_dt
                dy_adv_meters = v_eff * step_dt

                # 5. Stochastic diffusion displacement in meters: dE, dN ~ Normal(0, sigma)
                if diff_sigma > 0.0:
                    dE_meters = float(diff_rng.normal(0.0, diff_sigma))
                    dN_meters = float(diff_rng.normal(0.0, diff_sigma))
                else:
                    dE_meters = 0.0
                    dN_meters = 0.0

                # 6. Total horizontal displacement in local meters
                dx_total_meters = dx_adv_meters + dE_meters
                dy_total_meters = dy_adv_meters + dN_meters

                # 7. Convert total displacement to geographic degrees using WGS84 geodesics
                dlat_deg = meters_to_lat_deg(dy_total_meters)
                dlon_deg = meters_to_lon_deg(dx_total_meters, at_latitude=p.latitude)

                new_lat = p.latitude + dlat_deg
                new_lon = normalize_longitude(p.longitude + dlon_deg)

                # Geographic bounds sanity check [-90, 90]
                if new_lat > 90.0:
                    new_lat = 90.0
                elif new_lat < -90.0:
                    new_lat = -90.0

                # 8. Advance particle state
                p.latitude = new_lat
                p.longitude = new_lon
                p.timestamp = next_step_time
                p.age_seconds += step_dt

                state = ParticleState(
                    id=idx,
                    latitude=new_lat,
                    longitude=new_lon,
                    timestamp=next_step_time,
                    ensemble_member_id=p.ensemble_member_id,
                    age_seconds=p.age_seconds,
                    mass_kg=p.mass_kg,
                    is_active=True,
                    beached=False
                )
                trajectories[p.particle_id].append(state)
                step_states_snapshot.append(state)

            current_step_time = next_step_time
            step_statistics_list.append(
                compute_ensemble_step_statistics(current_step_time, step_states_snapshot)
            )

        result_trajectories = [
            Trajectory(
                particle_id=p_id,
                ensemble_member_id=states[0].ensemble_member_id if states else 0,
                states=states
            )
            for p_id, states in trajectories.items()
        ]

        sim_end_time = sim_t0 + timedelta(seconds=duration_seconds)
        return ForwardSimulationResult(
            start_time=sim_t0,
            end_time=sim_end_time,
            timestep_seconds=int(dt_seconds),
            particle_count=len(particles),
            trajectories=result_trajectories,
            step_statistics=step_statistics_list
        )

    def simulate_ensemble(
        self,
        source: Union[List[Particle], ParticleEnsemble, SlickDetectionInput, SentinelObservationDomain],
        start_time: Optional[Union[datetime, str]] = None,
        duration_seconds: float = 3600.0,
        dt_seconds: float = 600.0,
        ensemble_size: int = 1,
        particles_per_member: Optional[int] = None,
        diffusion_enabled: Optional[bool] = None,
        diffusion_coefficient_m2_s: Optional[float] = None,
        random_seed: Optional[int] = None,
        windage_fraction: Optional[float] = None,
        query_domain: Optional[EnvironmentalQueryDomain] = None,
    ) -> EnsembleSimulationResult:
        """
        Runs an ensemble of independent stochastic realizations for the same Feature 1 spill.

        Args:
            source: SlickDetectionInput, SentinelObservationDomain, or Particle set.
            start_time: Simulation start time T0.
            duration_seconds: Total duration in seconds (must be >= 0).
            dt_seconds: Forward timestep in seconds (must be > 0).
            ensemble_size: Number of ensemble realizations (must be >= 1).
            particles_per_member: Number of particles per ensemble member.
            diffusion_enabled: Whether to apply horizontal stochastic diffusion.
            diffusion_coefficient_m2_s: Kh in m^2/s.
            random_seed: Master random seed for reproducible ensemble generation.
            windage_fraction: Leeway factor.
            query_domain: Environmental query domain.

        Returns:
            EnsembleSimulationResult containing all member trajectories and step dispersion statistics.
        """
        if ensemble_size < 1:
            raise ValueError(f"ensemble_size must be >= 1, got: {ensemble_size}")
        if dt_seconds <= 0:
            raise ValueError(f"dt_seconds must be > 0, got: {dt_seconds}")
        if duration_seconds < 0:
            raise ValueError(f"duration_seconds must be >= 0, got: {duration_seconds}")

        eff_kh = (
            diffusion_coefficient_m2_s if diffusion_coefficient_m2_s is not None
            else self.settings.diffusion.horizontal_diffusivity_m2_s
        )
        if eff_kh < 0.0:
            raise ValueError(f"diffusion_coefficient_m2_s must be non-negative (>= 0), got: {eff_kh}")

        eff_diffusion_enabled = (
            diffusion_enabled if diffusion_enabled is not None
            else self.settings.diffusion.enable_stochastic_diffusion
        )

        # Spawn independent child seeds using SeedSequence
        master_seed = random_seed if random_seed is not None else self.settings.diffusion.random_seed
        if master_seed is not None:
            seed_seq = np.random.SeedSequence(master_seed)
            child_seeds = seed_seq.spawn(ensemble_size)
        else:
            child_seeds = [None] * ensemble_size

        num_p = particles_per_member or self.settings.forecast.particles_per_slick

        all_trajectories: List[Trajectory] = []

        for member_idx in range(ensemble_size):
            member_seed = int(child_seeds[member_idx].generate_state(1)[0]) if child_seeds[member_idx] else None

            # Seed particles for this ensemble member
            if isinstance(source, (SlickDetectionInput, SentinelObservationDomain)):
                member_particles = ParticleManager.seed_particles(
                    source=source,
                    num_particles=num_p,
                    random_seed=member_seed
                )
            elif isinstance(source, list):
                member_particles = [p.model_copy() for p in source]
            elif isinstance(source, ParticleEnsemble):
                member_particles = [
                    Particle(
                        particle_id=f"p_{p.id:04d}",
                        latitude=p.latitude,
                        longitude=p.longitude,
                        timestamp=source.timestamp,
                        ensemble_member_id=member_idx,
                        active=p.is_active,
                        age_seconds=p.age_seconds,
                        mass_kg=p.mass_kg
                    )
                    for p in source.particles
                ]
            else:
                raise ValueError(f"Unsupported source type for ensemble simulation: {type(source)}")

            # Assign member ID and globally unique particle IDs
            for p in member_particles:
                p.ensemble_member_id = member_idx
                p.particle_id = f"m{member_idx:02d}_{p.particle_id}"

            # Run forward advection + diffusion for this ensemble member
            sim_res = self.simulate_forward(
                initial_particles=member_particles,
                start_time=start_time,
                duration_seconds=duration_seconds,
                dt_seconds=dt_seconds,
                windage_fraction=windage_fraction,
                diffusion_enabled=eff_diffusion_enabled,
                diffusion_coefficient_m2_s=eff_kh,
                random_seed=member_seed,
                query_domain=query_domain
            )

            all_trajectories.extend(sim_res.trajectories)

        # Compute aggregate ensemble dispersion statistics across all members for each time step
        total_steps = len(all_trajectories[0].states) if all_trajectories and all_trajectories[0].states else 0
        aggregate_step_stats: List[EnsembleStepStatistics] = []

        for step_k in range(total_steps):
            particles_at_k = [
                traj.states[step_k]
                for traj in all_trajectories
                if step_k < len(traj.states)
            ]
            step_time = particles_at_k[0].timestamp if particles_at_k else normalize_to_utc(start_time or datetime.now())
            aggregate_step_stats.append(
                compute_ensemble_step_statistics(step_time, particles_at_k)
            )

        sim_t0 = all_trajectories[0].states[0].timestamp if all_trajectories else normalize_to_utc(start_time or datetime.now())
        sim_end_time = sim_t0 + timedelta(seconds=duration_seconds)

        return EnsembleSimulationResult(
            start_time=sim_t0,
            end_time=sim_end_time,
            timestep_seconds=int(dt_seconds),
            ensemble_size=ensemble_size,
            particles_per_member=num_p,
            total_trajectories_count=len(all_trajectories),
            trajectories=all_trajectories,
            step_statistics=aggregate_step_stats
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
                            timestamp=item.timestamp or datetime.now(),
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
                num_particles=self.settings.simulation.num_particles if hasattr(self.settings, "simulation") else 500,
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
        Returns time series snapshots of ParticleEnsemble objects.
        """
        duration = max((normalize_to_utc(end_time) - normalize_to_utc(start_time)).total_seconds(), 0.0)
        result = self.simulate_forward(
            initial_particles=initial_ensemble,
            start_time=start_time,
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


def simulate_forward(
    initial_particles: Union[List[Particle], ParticleEnsemble, SlickDetectionInput, SentinelObservationDomain],
    start_time: Optional[Union[datetime, str]] = None,
    duration_seconds: float = 3600.0,
    dt_seconds: float = 600.0,
    current_provider: Optional[EnvironmentalDataProvider] = None,
    wind_provider: Optional[EnvironmentalDataProvider] = None,
    windage_fraction: Optional[float] = None,
    diffusion_enabled: Optional[bool] = False,
    diffusion_coefficient_m2_s: Optional[float] = None,
    random_seed: Optional[int] = None,
    config: Optional[Feature2Settings] = None,
    query_domain: Optional[EnvironmentalQueryDomain] = None,
    step_callback: Optional[Callable[[Particle, float, float, datetime], None]] = None,
) -> ForwardSimulationResult:
    """
    Convenience functional interface for forward Lagrangian particle advection + diffusion.
    """
    settings = config or default_settings
    if current_provider is None:
        raise ValueError("current_provider is required for simulate_forward.")

    engine = ForwardSimulationEngine(
        currents_provider=current_provider,
        wind_provider=wind_provider,
        settings=settings
    )

    return engine.simulate_forward(
        initial_particles=initial_particles,
        start_time=start_time,
        duration_seconds=duration_seconds,
        dt_seconds=dt_seconds,
        windage_fraction=windage_fraction,
        diffusion_enabled=diffusion_enabled,
        diffusion_coefficient_m2_s=diffusion_coefficient_m2_s,
        random_seed=random_seed,
        query_domain=query_domain,
        step_callback=step_callback
    )


def simulate_ensemble(
    source: Union[List[Particle], ParticleEnsemble, SlickDetectionInput, SentinelObservationDomain],
    start_time: Optional[Union[datetime, str]] = None,
    duration_seconds: float = 3600.0,
    dt_seconds: float = 600.0,
    ensemble_size: int = 1,
    particles_per_member: Optional[int] = None,
    current_provider: Optional[EnvironmentalDataProvider] = None,
    wind_provider: Optional[EnvironmentalDataProvider] = None,
    windage_fraction: Optional[float] = None,
    diffusion_enabled: Optional[bool] = True,
    diffusion_coefficient_m2_s: Optional[float] = None,
    random_seed: Optional[int] = None,
    config: Optional[Feature2Settings] = None,
    query_domain: Optional[EnvironmentalQueryDomain] = None,
) -> EnsembleSimulationResult:
    """
    Convenience functional interface for forward stochastic ensemble simulations.
    """
    settings = config or default_settings
    if current_provider is None:
        raise ValueError("current_provider is required for simulate_ensemble.")

    engine = ForwardSimulationEngine(
        currents_provider=current_provider,
        wind_provider=wind_provider,
        settings=settings
    )

    return engine.simulate_ensemble(
        source=source,
        start_time=start_time,
        duration_seconds=duration_seconds,
        dt_seconds=dt_seconds,
        ensemble_size=ensemble_size,
        particles_per_member=particles_per_member,
        diffusion_enabled=diffusion_enabled,
        diffusion_coefficient_m2_s=diffusion_coefficient_m2_s,
        random_seed=random_seed,
        windage_fraction=windage_fraction,
        query_domain=query_domain
    )
