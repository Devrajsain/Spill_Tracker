"""
Forward oil-slick trajectory forecasting engine (Task 3E).
Coordinates single continuous forward Lagrangian ensemble advection with
stochastic diffusion from the observed SAR slick across configurable horizons
(+6h, +12h, +24h, +48h).
"""

from datetime import datetime, timedelta, timezone
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from ..schemas.input_schema import SlickDetectionInput, CentroidCoordinates, GeoJSONGeometry
from ..schemas.output_schema import (
    ForecastAnalysisResult,
    ForecastHorizonResult,
    ForecastStepResult,
    ForecastUncertainty,
    SpatialUncertainty,
    ScientificDisclaimers,
)
from ..schemas.simulation_schema import (
    Particle,
    ParticleState,
    ParticleEnsemble,
    ForwardSimulationResult,
    EnsembleSimulationResult,
)
from ..data.base import EnvironmentalDataProvider
from ..data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from ..data.coord_utils import normalize_longitude
from ..data.time_utils import normalize_to_utc
from ..geo.coordinates import (
    EARTH_RADIUS_KM,
    meters_to_lat_deg,
    meters_to_lon_deg,
    haversine_distance_km,
)
from ..simulation.forward.engine import ForwardSimulationEngine
from ..simulation.particles import ParticleManager
from ..uncertainty.spatial_error import SpatialUncertaintyEstimator
from ..config import Feature2Settings, default_settings
from ..logging_config import logger


def circular_mean_longitude(lons_deg: np.ndarray) -> float:
    """
    Computes dateline-safe circular mean longitude in decimal degrees [-180, 180].
    Prevents artificial longitude jumps near the +/- 180 antimeridian.
    """
    if len(lons_deg) == 0:
        return 0.0
    lons_rad = np.radians(lons_deg)
    sin_mean = float(np.mean(np.sin(lons_rad)))
    cos_mean = float(np.mean(np.cos(lons_rad)))
    mean_rad = math.atan2(sin_mean, cos_mean)
    return normalize_longitude(math.degrees(mean_rad))


class ForwardForecaster:
    """
    Simulates forward trajectory advection and horizontal stochastic diffusion
    starting from the observed Feature 1 slick geometry at T0.
    Executes a single continuous ensemble simulation and extracts statistics
    at requested horizons (+6h, +12h, +24h, +48h).
    """

    def __init__(
        self,
        current_provider: Optional[EnvironmentalDataProvider] = None,
        wind_provider: Optional[EnvironmentalDataProvider] = None,
        simulation_engine: Optional[ForwardSimulationEngine] = None,
        settings: Optional[Feature2Settings] = None,
    ):
        self.settings = settings or default_settings

        if isinstance(current_provider, ForwardSimulationEngine):
            simulation_engine = current_provider
            current_provider = None

        if simulation_engine is not None:
            self.engine = simulation_engine
            self.current_provider = simulation_engine.currents_provider
            self.wind_provider = simulation_engine.wind_provider
        elif current_provider is not None:
            self.current_provider = current_provider
            self.wind_provider = wind_provider
            self.engine = ForwardSimulationEngine(
                currents_provider=current_provider,
                wind_provider=wind_provider,
                settings=self.settings
            )
        else:
            raise ValueError("Either current_provider or simulation_engine must be provided.")

    def predict(
        self,
        slick: Union[SlickDetectionInput, SentinelObservationDomain, Dict[str, Any]],
        forecast_horizons_hours: Optional[List[float]] = None,
        ensemble_size: Optional[int] = None,
        particles_per_slick: Optional[int] = None,
        dt_seconds: Optional[float] = None,
        random_seed: Optional[int] = None,
        origin_candidate_id: Optional[str] = None,
        query_domain: Optional[EnvironmentalQueryDomain] = None,
        diffusion_enabled: Optional[bool] = None,
        diffusion_coefficient_m2_s: Optional[float] = None,
        windage_fraction: Optional[float] = None,
    ) -> ForecastAnalysisResult:
        """
        Executes a single continuous forward ensemble simulation and produces
        structured predictions across target lead times (+6h, +12h, +24h, +48h).

        Args:
            slick: Feature 1 SlickDetectionInput, SentinelObservationDomain, or raw dict.
            forecast_horizons_hours: Target lead times (defaults to config: [6, 12, 24, 48]).
            ensemble_size: Number of ensemble realizations (defaults to config).
            particles_per_slick: Number of particles per ensemble member (defaults to config).
            dt_seconds: Forward simulation timestep in seconds.
            random_seed: Master seed for deterministic reproducibility.
            origin_candidate_id: Optional origin candidate hypothesis ID.
            query_domain: Optional pre-configured environmental query domain.
            diffusion_enabled: Toggle for horizontal stochastic diffusion.
            diffusion_coefficient_m2_s: Diffusivity Kh in m^2/s.
            windage_fraction: Leeway multiplier for surface windage.

        Returns:
            ForecastAnalysisResult containing both horizon-keyed and list-based results.
        """
        # 1. Resolve Slick input and observation anchor T0
        if isinstance(slick, dict):
            slick_input = SlickDetectionInput(**slick)
        elif isinstance(slick, SlickDetectionInput):
            slick_input = slick
        elif isinstance(slick, SentinelObservationDomain):
            # Wrap as pseudo slick detection input with polygon from bounding box
            poly_coords = [
                [slick.min_lon, slick.min_lat],
                [slick.max_lon, slick.min_lat],
                [slick.max_lon, slick.max_lat],
                [slick.min_lon, slick.max_lat],
                [slick.min_lon, slick.min_lat],
            ]
            slick_input = SlickDetectionInput(
                spill_id=slick.spill_id,
                observation_time=slick.observation_time,
                centroid=CentroidCoordinates(latitude=slick.centroid_lat, longitude=slick.centroid_lon),
                area_sq_km=slick.area_sq_km or 1.0,
                perimeter_km=slick.perimeter_km or 4.0,
                geometry=GeoJSONGeometry(type="Polygon", coordinates=[poly_coords])
            )
        else:
            raise ValueError(f"Unsupported slick input type: {type(slick)}")

        spill_id = slick_input.spill_id
        t0 = normalize_to_utc(slick_input.observation_time)
        centroid_0 = slick_input.centroid

        # 2. Configuration resolution
        horizons = sorted(
            forecast_horizons_hours if forecast_horizons_hours is not None
            else self.settings.forecast.forecast_horizons_hours
        )
        if not horizons or any(h <= 0 for h in horizons):
            raise ValueError(f"Forecast horizons must be a non-empty list of positive hours, got: {horizons}")

        max_horizon_h = max(horizons)
        duration_s = max_horizon_h * 3600.0

        step_dt = (
            float(dt_seconds) if dt_seconds is not None
            else float(self.settings.forecast.simulation_step_seconds)
        )
        if step_dt <= 0:
            raise ValueError(f"dt_seconds must be > 0, got: {step_dt}")

        n_members = (
            ensemble_size if ensemble_size is not None
            else self.settings.forecast.forecast_ensemble_size
        )
        n_particles = (
            particles_per_slick if particles_per_slick is not None
            else self.settings.forecast.particles_per_slick
        )
        master_seed = (
            random_seed if random_seed is not None
            else self.settings.random_seed
        )

        eff_diffusion = (
            diffusion_enabled if diffusion_enabled is not None
            else self.settings.diffusion.enable_stochastic_diffusion
        )
        eff_kh = (
            diffusion_coefficient_m2_s if diffusion_coefficient_m2_s is not None
            else self.settings.diffusion.horizontal_diffusivity_m2_s
        )

        # 3. Dynamic Forecast Environmental Domain
        eff_query_domain = query_domain
        if eff_query_domain is None:
            sentinel_domain = SentinelObservationDomain.from_feature1_input(slick_input)
            eff_query_domain = EnvironmentalQueryDomain.from_sentinel_observation(
                sentinel_domain=sentinel_domain,
                buffer_distance_km=self.settings.forecast.forecast_buffer_km,
                forecast_horizon_hours=max_horizon_h
            )

        logger.info(
            f"Executing continuous forward forecast for {spill_id} across horizons "
            f"{horizons}h (duration={duration_s/3600.0}h, members={n_members}, dt={step_dt}s)"
        )

        # 4. Single continuous forward ensemble simulation
        ensemble_result = self.engine.simulate_ensemble(
            source=slick_input,
            start_time=t0,
            duration_seconds=duration_s,
            dt_seconds=step_dt,
            ensemble_size=n_members,
            particles_per_member=n_particles,
            diffusion_enabled=eff_diffusion,
            diffusion_coefficient_m2_s=eff_kh,
            random_seed=master_seed,
            windage_fraction=windage_fraction,
            query_domain=eff_query_domain
        )

        # 5. Extract statistics and build predictions for each requested horizon
        horizon_results: Dict[str, ForecastHorizonResult] = {}
        legacy_step_results: List[ForecastStepResult] = []
        earth_radius_m = EARTH_RADIUS_KM * 1000.0

        for h in horizons:
            key = f"{int(h) if h.is_integer() else h}h"
            target_time = t0 + timedelta(hours=h)
            target_seconds = h * 3600.0
            step_k = min(int(round(target_seconds / step_dt)), len(ensemble_result.step_statistics) - 1)

            # Collect particle states at this step across all trajectories
            particles_at_k: List[ParticleState] = []
            for traj in ensemble_result.trajectories:
                if step_k < len(traj.states):
                    particles_at_k.append(traj.states[step_k])

            total_count = len(particles_at_k)
            active_particles = [
                p for p in particles_at_k
                if getattr(p, "is_active", getattr(p, "active", True)) and not getattr(p, "beached", False)
            ]
            active_count = len(active_particles)
            active_fraction = active_count / float(total_count) if total_count > 0 else 0.0

            # Determine validity and quality
            min_act = self.settings.forecast.minimum_active_fraction
            high_thresh = self.settings.forecast.quality_threshold_high
            med_thresh = self.settings.forecast.quality_threshold_medium

            if active_fraction >= high_thresh:
                quality = "high"
            elif active_fraction >= med_thresh:
                quality = "medium"
            else:
                quality = "low"

            is_valid = (active_fraction >= min_act) and (active_count > 0)
            reason = None if is_valid else (
                "insufficient_active_particles" if total_count > 0 else "simulation_trajectory_empty"
            )

            # Compute centroid, spatial covariance, and uncertainty ellipse
            if active_count > 0:
                lats = np.array([p.latitude for p in active_particles], dtype=float)
                lons = np.array([p.longitude for p in active_particles], dtype=float)

                mean_lat = float(np.mean(lats))
                mean_lon = circular_mean_longitude(lons)

                # Metric displacements relative to circular mean
                mean_lat_rad = math.radians(mean_lat)
                cos_lat = max(math.cos(mean_lat_rad), 1e-6)

                # Handle dateline wrapping in offset calculation
                d_lon_deg = (lons - mean_lon + 180.0) % 360.0 - 180.0
                dE = d_lon_deg * (math.pi / 180.0) * earth_radius_m * cos_lat
                dN = (lats - mean_lat) * (math.pi / 180.0) * earth_radius_m
                pts_m = np.column_stack([dE, dN])

                if active_count >= 2:
                    cov_matrix = np.cov(pts_m, rowvar=False)
                    var_e = float(cov_matrix[0, 0])
                    var_n = float(cov_matrix[1, 1])
                    cov_en = float(cov_matrix[0, 1])
                    spread_r_m = float(math.sqrt(max(var_e + var_n, 0.0)))

                    eigenvalues, eigenvectors = np.linalg.eigh(cov_matrix)
                    order = eigenvalues.argsort()[::-1]
                    eigenvalues = np.maximum(eigenvalues[order], 1e-6)
                    eigenvectors = eigenvectors[:, order]

                    # Covariance-derived uncertainty ellipse
                    semi_major_km = float(math.sqrt(5.991 * eigenvalues[0]) / 1000.0)
                    semi_minor_km = float(math.sqrt(5.991 * eigenvalues[1]) / 1000.0)
                    angle_rad = math.atan2(eigenvectors[0, 0], eigenvectors[1, 0])
                    orientation_deg = float(math.degrees(angle_rad) % 360.0)
                else:
                    var_e = 0.0
                    var_n = 0.0
                    cov_en = 0.0
                    spread_r_m = 0.0
                    semi_major_km = 0.5
                    semi_minor_km = 0.5
                    orientation_deg = 0.0

                # Compute mean drift speed and direction relative to T0
                d_lon0_deg = (mean_lon - centroid_0.longitude + 180.0) % 360.0 - 180.0
                dE0 = d_lon0_deg * (math.pi / 180.0) * earth_radius_m * cos_lat
                dN0 = (mean_lat - centroid_0.latitude) * (math.pi / 180.0) * earth_radius_m
                drift_dist_km = math.sqrt(dE0**2 + dN0**2) / 1000.0
                drift_speed_kmh = drift_dist_km / h if h > 0 else 0.0
                drift_dir_deg = float(math.degrees(math.atan2(dE0, dN0)) % 360.0)

                # Uncertainty polygon representation
                uncertainty_obj = SpatialUncertaintyEstimator.compute_dispersion_ellipse(
                    [(p.latitude, p.longitude) for p in active_particles]
                )
            else:
                # Fallback for deactivation
                mean_lat = centroid_0.latitude
                mean_lon = centroid_0.longitude
                var_e = 0.0
                var_n = 0.0
                cov_en = 0.0
                spread_r_m = 0.0
                semi_major_km = 0.0
                semi_minor_km = 0.0
                orientation_deg = 0.0
                drift_speed_kmh = 0.0
                drift_dir_deg = 0.0
                uncertainty_obj = SpatialUncertaintyEstimator.compute_dispersion_ellipse([])

            uncertainty_info = ForecastUncertainty(
                radius_km=round(spread_r_m / 1000.0, 3),
                semi_major_km=round(semi_major_km, 3),
                semi_minor_km=round(semi_minor_km, 3),
                orientation_deg=round(orientation_deg, 2),
                uncertainty_polygon=uncertainty_obj.uncertainty_polygon
            )

            pred_centroid = CentroidCoordinates(
                latitude=round(mean_lat, 6),
                longitude=round(mean_lon, 6)
            )

            horizon_res = ForecastHorizonResult(
                lead_time_hours=float(h),
                forecast_time=target_time,
                valid=is_valid,
                reason=reason,
                centroid=pred_centroid,
                uncertainty=uncertainty_info,
                covariance_matrix=[
                    [round(var_e, 2), round(cov_en, 2)],
                    [round(cov_en, 2), round(var_n, 2)]
                ],
                active_particle_count=active_count,
                total_particle_count=total_count,
                active_fraction=round(active_fraction, 4),
                quality=quality,
                mean_drift_speed_kmh=round(drift_speed_kmh, 3),
                mean_drift_direction_deg=round(drift_dir_deg, 2),
                predicted_slick_polygon=uncertainty_obj.uncertainty_polygon
            )
            horizon_results[key] = horizon_res

            # Also assemble legacy ForecastStepResult
            legacy_step_results.append(
                ForecastStepResult(
                    lead_time_hours=float(h),
                    forecast_time_utc=target_time,
                    predicted_centroid=pred_centroid,
                    predicted_slick_polygon=uncertainty_obj.uncertainty_polygon,
                    spatial_uncertainty=uncertainty_obj,
                    mean_drift_speed_kmh=round(drift_speed_kmh, 3),
                    mean_drift_direction_deg=round(drift_dir_deg, 2)
                )
            )

        # 6. Assemble provenance and metadata
        provenance = {
            "current_source": getattr(self.current_provider, "provider_name", "unknown_currents"),
            "wind_source": getattr(self.wind_provider, "provider_name", "none") if self.wind_provider else "none",
            "environmental_data_mode": "operational_forecast" if "forecast" in getattr(self.current_provider, "provider_name", "").lower() else "provider_query",
        }

        metadata = {
            "forecast_start": t0.isoformat(),
            "forecast_end": (t0 + timedelta(hours=max_horizon_h)).isoformat(),
            "requested_horizons_hours": horizons,
            "ensemble_size": n_members,
            "particles_per_slick": n_particles,
            "random_seed": master_seed,
            "windage_fraction": windage_fraction if windage_fraction is not None else self.settings.windage.leeway_factor,
            "diffusion_coefficient_m2_s": eff_kh if eff_diffusion else 0.0,
            "simulation_dt_seconds": step_dt,
            "origin_candidate_id": origin_candidate_id,
        }

        return ForecastAnalysisResult(
            spill_id=spill_id,
            observation_time=t0,
            horizons=legacy_step_results,
            forecast=horizon_results,
            origin_candidate_id=origin_candidate_id,
            provenance=provenance,
            metadata=metadata,
            disclaimers=ScientificDisclaimers(
                methodology="Forward Lagrangian particle advection with horizontal Fickian stochastic diffusion.",
                confidence_score_definition="Forecast results represent ensemble dispersion spread and uncertainty zones, NOT exact future positions.",
                uncertainty_notice="Predicted positions reflect model physics and environmental forcing; they do not represent exact boundaries.",
                limitations=[
                    "Forecast trajectories depend strictly on environmental current and wind forecast accuracy.",
                    "Oil weathering kinetics (evaporation, emulsification, dissolution) are not coupled.",
                    "Coastline beaching and shoreline interaction physics are not modeled.",
                    "Sub-grid turbulence and unresolved coastal bathymetry may introduce spatial displacement bias."
                ]
            )
        )


def predict_slick_forecast(
    slick: Union[SlickDetectionInput, SentinelObservationDomain, Dict[str, Any]],
    current_provider: EnvironmentalDataProvider,
    wind_provider: Optional[EnvironmentalDataProvider] = None,
    forecast_horizons_hours: Optional[List[float]] = None,
    ensemble_size: Optional[int] = None,
    particles_per_slick: Optional[int] = None,
    dt_seconds: Optional[float] = None,
    random_seed: Optional[int] = None,
    origin_candidate_id: Optional[str] = None,
    query_domain: Optional[EnvironmentalQueryDomain] = None,
    config: Optional[Feature2Settings] = None,
) -> ForecastAnalysisResult:
    """
    Convenience functional interface for forward oil slick forecasting.
    """
    forecaster = ForwardForecaster(
        current_provider=current_provider,
        wind_provider=wind_provider,
        settings=config or default_settings
    )

    return forecaster.predict(
        slick=slick,
        forecast_horizons_hours=forecast_horizons_hours,
        ensemble_size=ensemble_size,
        particles_per_slick=particles_per_slick,
        dt_seconds=dt_seconds,
        random_seed=random_seed,
        origin_candidate_id=origin_candidate_id,
        query_domain=query_domain
    )
