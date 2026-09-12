"""
Feature 2 End-to-End Pipeline Service (Task 3F).
Coordinates:
  1. Feature 1 SAR slick validation & UTC normalization
  2. SentinelObservationDomain derivation
  3. Dynamic historical & forecast environmental domain query derivation
  4. Backward Lagrangian reconstruction & candidate origin estimation (Task 3C/3D)
  5. Forward Lagrangian ensemble slick trajectory forecasting (+6h, +12h, +24h, +48h) (Task 3E)
  6. Consolidated Feature2PipelineResponse & GeoJSON export
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

from ..config import Feature2Settings, default_settings, validate_production_data_sources
from ..data.base import EnvironmentalDataProvider
from ..data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from ..data.time_utils import normalize_to_utc
from ..exceptions import EnvironmentalCoverageError, ConfigurationError
from ..forecast.forecaster import ForwardForecaster
from ..logging_config import logger
from ..origin.estimator import OriginEstimator
from ..schemas.input_schema import SlickDetectionInput, CentroidCoordinates
from ..schemas.feature1_adapter import parse_feature1_input
from ..schemas.output_schema import (
    CandidateOrigin,
    Feature2PipelineResponse,
    ForecastAnalysisResult,
    OriginAnalysisResult,
    OriginEstimationResult,
    ReleaseTimeWindow,
    ScientificDisclaimers,
    LatLonCoord,
    ObservationOutputSummary,
    BoundingBoxSummary,
    EnvironmentDomainSummary,
    TimeWindowSummary,
    EnvironmentOutputSummary,
    EnvironmentalFieldProvenance,
    OriginUncertaintySummary,
    OriginCandidateSummary,
    OriginOutputSummary,
    ForecastHorizonSummary,
    ForecastInitializationSummary,
    ForecastEnsembleSummary,
    ForecastOutputSummary,
    QualityAssessmentSummary,
    ReproducibilitySummary,
    UnifiedFeature2Result,
)
from ..uncertainty.spatial_error import SpatialUncertaintyEstimator


class Feature2PipelineService:
    """
    Central service coordinating backward origin tracing and forward slick trajectory forecasting.
    Reuses existing physics engines, environmental domain builders, and uncertainty estimators.
    """

    def __init__(
        self,
        origin_estimator: OriginEstimator,
        forecaster: ForwardForecaster,
        settings: Optional[Feature2Settings] = None,
    ):
        self.origin_estimator = origin_estimator
        self.forecaster = forecaster
        self.settings = settings or default_settings
        validate_production_data_sources(self.settings)

        if self.settings.environment == "production":
            from ..data.wind.mock import MockWindProvider
            from ..data.currents.mock import MockCurrentsProvider
            if (
                isinstance(self.origin_estimator.wind_provider, MockWindProvider) or
                isinstance(self.forecaster.wind_provider, MockWindProvider)
            ):
                raise ConfigurationError("Production mode strictly forbids MockWindProvider.")
            if (
                isinstance(self.origin_estimator.currents_provider, MockCurrentsProvider) or
                isinstance(self.forecaster.current_provider, MockCurrentsProvider)
            ):
                raise ConfigurationError("Production mode strictly forbids MockCurrentsProvider.")

    def trace_origin(
        self,
        slick: Union[SlickDetectionInput, Dict[str, Any]],
        query_domain: Optional[EnvironmentalQueryDomain] = None,
    ) -> OriginAnalysisResult:
        """
        Executes inverse reconstruction across candidate release windows before observation time T0.
        Produces ranked origin candidates, spatial dispersion uncertainty, and plausible release window.
        """
        validate_production_data_sources(self.settings)
        slick = parse_feature1_input(slick)
        obs_time_utc = normalize_to_utc(slick.observation_time)
        curr_provider = self.origin_estimator.currents_provider
        wind_provider = self.origin_estimator.wind_provider
        is_mock = (
            "mock" in type(curr_provider).__name__.lower()
            or "mock" in type(wind_provider).__name__.lower()
            or self.settings.environment == "testing"
            or self.settings.data.currents_provider == "mock"
        )
        mode_str = "MOCK" if is_mock else "REAL"

        # Derive dynamic historical query domain anchored to Feature 1 observation
        obs_domain = SentinelObservationDomain.from_slick_input(slick)
        hist_horizon_h = self.settings.backward.max_backtrack_hours
        hist_buffer_km = max(self.settings.backward.convergence_cluster_eps_km * 25.0, 50.0)

        hist_domain = query_domain or EnvironmentalQueryDomain.from_sentinel_observation(
            obs_domain,
            buffer_distance_km=hist_buffer_km,
            historical_horizon_hours=hist_horizon_h,
        )

        bbox = hist_domain.environmental_bbox
        logger.info("======================================================")
        logger.info(f"FEATURE2 DATA MODE: {mode_str}")
        logger.info("BACKTRACKING ENVIRONMENTAL MODEL:")
        logger.info("  Historical ocean current = CMEMS (Copernicus Marine)")
        logger.info("  Historical/operational wind = GFS (NOAA/Open-Meteo)")
        logger.info("QUERY PARAMETERS:")
        logger.info(f"  Spill ID: {slick.spill_id}")
        logger.info(f"  Detection Timestamp (T0): {obs_time_utc.isoformat()}")
        logger.info(f"  Backtrack Horizon: {hist_horizon_h} hours (T0 - {hist_horizon_h}h -> T0)")
        logger.info(f"  Simulation dt: {self.settings.backward.simulation_step_seconds}s")
        logger.info(f"  Bounding Box: min_lat={bbox[0]:.4f}, max_lat={bbox[1]:.4f}, min_lon={bbox[2]:.4f}, max_lon={bbox[3]:.4f}")
        logger.info(f"  Currents Provider: {getattr(curr_provider, 'provider_name', type(curr_provider).__name__)} (dataset: {getattr(getattr(curr_provider, 'config', None), 'dataset_id', 'N/A')})")
        logger.info(f"  Wind Provider: {getattr(wind_provider, 'provider_name', type(wind_provider).__name__)} (mode: {getattr(wind_provider, 'mode', 'N/A')})")
        logger.info("======================================================")

        # Validate environmental provider domain coverage
        if hasattr(self.origin_estimator.currents_provider, "fetch_grid"):
            covered = self.origin_estimator.currents_provider.fetch_grid(hist_domain)
            if covered is False:
                raise EnvironmentalCoverageError(
                    f"Currents provider '{self.origin_estimator.currents_provider.provider_name}' "
                    f"does not cover the required historical spacetime domain: {hist_domain.environmental_bbox}"
                )
        if hasattr(self.origin_estimator.wind_provider, "fetch_grid"):
            covered_wind = self.origin_estimator.wind_provider.fetch_grid(hist_domain)
            if covered_wind is False:
                raise EnvironmentalCoverageError(
                    f"Wind provider '{self.origin_estimator.wind_provider.provider_name}' "
                    f"does not cover the required historical spacetime domain: {hist_domain.environmental_bbox}"
                )

        # Execute full origin estimation (reconstruction -> clustering -> scoring -> release window)
        est_result: OriginEstimationResult = self.origin_estimator.estimate_origins(
            source=slick,
            observation_time=obs_time_utc,
            spill_id=slick.spill_id,
            max_backtrack_hours=hist_horizon_h,
            candidate_interval_hours=self.settings.backward.candidate_time_step_hours,
            dt_seconds=float(self.settings.backward.simulation_step_seconds),
            windage_fraction=self.settings.windage.leeway_factor,
            query_domain=hist_domain,
        )

        # Map internal OriginCandidate objects to API CandidateOrigin schema
        candidate_origins: List[CandidateOrigin] = []
        for cand in est_result.candidates:
            semi_maj = cand.semi_major_axis_km or cand.uncertainty_radius_km or 1.0
            semi_min = cand.semi_minor_axis_km or cand.uncertainty_radius_km or 1.0
            orient = cand.orientation_deg or 0.0

            spatial_unc = SpatialUncertaintyEstimator.from_parameters(
                mean_lat=cand.latitude,
                mean_lon=cand.longitude,
                semi_major_km=semi_maj,
                semi_minor_km=semi_min,
                orientation_deg=orient,
            )

            if est_result.release_time_window:
                rel_win = ReleaseTimeWindow(
                    earliest_utc=est_result.release_time_window.start,
                    latest_utc=est_result.release_time_window.end,
                    peak_evidence_utc=est_result.release_time_window.peak_evidence_time or cand.release_time,
                    window_duration_hours=est_result.release_time_window.duration_hours or 0.0,
                )
            else:
                interval_h = self.settings.backward.candidate_time_step_hours
                half_delta = timedelta(hours=interval_h / 2.0)
                rel_win = ReleaseTimeWindow(
                    earliest_utc=cand.release_time - half_delta,
                    latest_utc=cand.release_time + half_delta,
                    peak_evidence_utc=cand.release_time,
                    window_duration_hours=interval_h,
                )

            candidate_origins.append(
                CandidateOrigin(
                    cluster_id=cand.cluster_id,
                    estimated_centroid=CentroidCoordinates(
                        latitude=cand.latitude,
                        longitude=cand.longitude,
                    ),
                    spatial_uncertainty=spatial_unc,
                    release_time_window=rel_win,
                    confidence_score=cand.candidate_score,
                    particle_support_ratio=cand.cluster_fraction,
                    environmental_consistency_score=cand.coverage_score,
                )
            )

        return OriginAnalysisResult(
            spill_id=slick.spill_id,
            observation_time=obs_time_utc,
            search_horizon_hours=hist_horizon_h,
            candidate_origins=candidate_origins,
            origin_estimation=est_result,
            best_candidate=est_result.best_candidate,
            candidates=est_result.candidates,
            release_time_window=est_result.release_time_window,
            disclaimers=est_result.disclaimers,
        )

    def predict_forecast(
        self,
        slick: Union[SlickDetectionInput, Dict[str, Any]],
        origin_candidate_id: Optional[str] = None,
        query_domain: Optional[EnvironmentalQueryDomain] = None,
    ) -> ForecastAnalysisResult:
        """
        Executes continuous forward Lagrangian ensemble simulation from the observed Feature 1 slick geometry.
        """
        validate_production_data_sources(self.settings)
        slick = parse_feature1_input(slick)
        logger.info(f"[Feature2Pipeline] Predicting forward forecast for spill '{slick.spill_id}'")
        # Validate forward forecast environmental provider coverage
        fc_curr = getattr(self.forecaster, "current_provider", None) or getattr(getattr(self.forecaster, "engine", None), "currents_provider", None)
        fc_wind = getattr(self.forecaster, "wind_provider", None) or getattr(getattr(self.forecaster, "engine", None), "wind_provider", None)
        if hasattr(fc_curr, "fetch_grid") and query_domain:
            fc_curr.fetch_grid(query_domain)
        if hasattr(fc_wind, "fetch_grid") and query_domain:
            fc_wind.fetch_grid(query_domain)

        return self.forecaster.predict(
            slick=slick,
            origin_candidate_id=origin_candidate_id,
            query_domain=query_domain,
        )

    def run_pipeline(
        self,
        slick: Union[SlickDetectionInput, Dict[str, Any]],
    ) -> Feature2PipelineResponse:
        """
        Executes full end-to-end Feature 2 pipeline:
          1. Trace origin candidates backward in time from T0
          2. Predict slick trajectory forward in time (+6h, +12h, +24h, +48h) starting from observed slick at T0
          3. Consolidate into structured Feature2PipelineResponse
        """
        validate_production_data_sources(self.settings)
        slick = parse_feature1_input(slick)
        obs_time_utc = normalize_to_utc(slick.observation_time)
        logger.info(f"[Feature2Pipeline] Running complete pipeline for spill '{slick.spill_id}'")

        # Derive dynamic environmental domain for reporting
        obs_domain = SentinelObservationDomain.from_slick_input(slick)
        hist_horizon_h = self.settings.backward.max_backtrack_hours
        hist_buffer_km = max(self.settings.backward.convergence_cluster_eps_km * 25.0, 50.0)

        hist_domain = EnvironmentalQueryDomain.from_sentinel_observation(
            obs_domain,
            buffer_distance_km=hist_buffer_km,
            historical_horizon_hours=hist_horizon_h,
            forecast_horizon_hours=48.0
        )

        # 1. Backward origin estimation
        origin_res = self.trace_origin(slick, query_domain=hist_domain)

        # 2. Forward forecast (primary initial condition is the observed Feature 1 slick at T0)
        best_cand_id = origin_res.best_candidate.candidate_id if origin_res.best_candidate else None
        forecast_res = self.predict_forecast(slick, origin_candidate_id=best_cand_id, query_domain=hist_domain)

        # 3. Build Unified Feature 2 Result Sections
        # 3.1 Observation
        observation_summary = ObservationOutputSummary(
            observation_time=obs_time_utc,
            centroid=LatLonCoord(lat=slick.centroid.latitude, lon=slick.centroid.longitude),
            geometry=slick.geometry,
            area_km2=slick.area_sq_km,
            perimeter_km=slick.perimeter_km,
        )

        # 3.2 Environment Domain & Provenance
        hist_wind_prov = getattr(self.origin_estimator.wind_provider, "provenance", {})
        hist_curr_prov = getattr(self.origin_estimator.currents_provider, "provenance", {})
        fc_wind_prov = getattr(getattr(self.forecaster, "wind_provider", None), "provenance", {}) or getattr(getattr(getattr(self.forecaster, "engine", None), "wind_provider", None), "provenance", {})
        fc_curr_prov = getattr(getattr(self.forecaster, "current_provider", None), "provenance", {}) or getattr(getattr(getattr(self.forecaster, "engine", None), "currents_provider", None), "provenance", {})

        def _classify_source(src_type: Any, cache_st: Any) -> str:
            st = str(src_type).lower()
            cs = str(cache_st).lower()
            if "local_netcdf" in st or "fixture" in st or cs == "direct":
                return "LOCAL_TEST_FIXTURE"
            elif cs == "hit" or "cache" in st:
                return "LOCAL_CACHE"
            elif "remote" in st or "download" in st or cs == "miss":
                return "LIVE_REMOTE"
            return "LOCAL_TEST_FIXTURE"

        def _make_field_prov(prov: Dict[str, Any], field_type: str, mode: str, req_win: Any) -> EnvironmentalFieldProvenance:
            src_type = prov.get("source_type", "local_netcdf")
            cache_st = prov.get("cache_status", "direct")
            classified = _classify_source(src_type, cache_st)

            t_dom = prov.get("temporal_domain", {})
            act_range = None
            if t_dom.get("start") and t_dom.get("end"):
                try:
                    act_range = TimeWindowSummary(
                        start=datetime.fromisoformat(str(t_dom["start"])),
                        end=datetime.fromisoformat(str(t_dom["end"])),
                    )
                except Exception:
                    pass

            req_range = None
            if req_win:
                req_range = TimeWindowSummary(
                    start=req_win.start,
                    end=req_win.end,
                )

            p_name_raw = str(prov.get("source", prov.get("provider_name", mode))).lower()
            model_src = None
            access_prov = None
            if "gfs" in p_name_raw:
                model_src = "GFS"
                access_prov = "Open-Meteo"
            elif "era5" in p_name_raw:
                model_src = "ERA5"
                access_prov = "ECMWF CDS API"
            elif "copernicus" in p_name_raw or "cmems" in p_name_raw or "glorys" in p_name_raw:
                model_src = "Copernicus Global Ocean Physics Analysis and Forecast"
                access_prov = "Copernicus Marine Data Store"
            elif "mock" in p_name_raw:
                model_src = "MockSynthetic"
                access_prov = "LocalMock"
            elif "local" in p_name_raw:
                model_src = "LocalNetCDF"
                access_prov = "LocalFilesystem"

            return EnvironmentalFieldProvenance(
                provider_name=prov.get("source", prov.get("provider_name", mode)),
                dataset_id=prov.get("product", prov.get("dataset_name", "grid")),
                model_source=model_src,
                access_provider=access_prov,
                field_type=field_type,
                data_category=mode,
                source_type=classified,
                cache_status=str(cache_st),
                requested_time_range=req_range,
                actual_time_range=act_range,
                filepath=prov.get("active_filepath"),
                used_in_numerical_simulation=True,
                notes="Applied in numerical Lagrangian simulation." if classified == "LOCAL_TEST_FIXTURE" else f"Active remote/cached {mode} stream."
            )

        hist_win_summary = TimeWindowSummary(
            start=hist_domain.historical_start_time,
            end=hist_domain.historical_end_time,
        )
        fc_win_summary = TimeWindowSummary(
            start=hist_domain.forecast_start_time,
            end=hist_domain.forecast_end_time,
        )

        fields_provenance = {
            "historical_wind": _make_field_prov(hist_wind_prov, "surface_wind", "historical", hist_win_summary),
            "historical_currents": _make_field_prov(hist_curr_prov, "ocean_currents", "historical", hist_win_summary),
            "forecast_wind": _make_field_prov(fc_wind_prov, "surface_wind", "forecast", fc_win_summary),
            "forecast_currents": _make_field_prov(fc_curr_prov, "ocean_currents", "forecast", fc_win_summary),
        }

        fc_w_class = fields_provenance["forecast_wind"].source_type
        fc_c_class = fields_provenance["forecast_currents"].source_type

        if fc_w_class == "LOCAL_TEST_FIXTURE" and fc_c_class == "LOCAL_TEST_FIXTURE":
            fc_prov_status = "HISTORICAL_REPLAY_FIXTURE"
            fc_prov_notes = "Historical replay forecast: forecast forcing for 2018 is supplied by local historical fixture data because current operational GFS does not archive the 2018 forecast cycle."
        elif fc_w_class in ("LIVE_REMOTE", "LOCAL_CACHE") and fc_c_class in ("LIVE_REMOTE", "LOCAL_CACHE"):
            fc_prov_status = "LIVE_OPERATIONAL"
            fc_prov_notes = "Live operational forecast: forecast forcing is supplied directly by operational atmospheric and oceanographic forecast models."
        else:
            fc_prov_status = "MIXED"
            fc_prov_notes = "Mixed forecast forcing: forecast fields are partially supplied by local historical fixtures and partially by operational data."

        environment_summary = EnvironmentOutputSummary(
            domain=EnvironmentDomainSummary(
                bbox=BoundingBoxSummary(
                    min_lat=hist_domain.min_lat,
                    max_lat=hist_domain.max_lat,
                    min_lon=hist_domain.min_lon,
                    max_lon=hist_domain.max_lon,
                ),
                buffer_km=hist_domain.buffer_distance_km,
            ),
            historical_window=hist_win_summary,
            forecast_window=fc_win_summary,
            forecast_provenance_status=fc_prov_status,
            forecast_provenance_notes=fc_prov_notes,
            fields=fields_provenance,
            providers={
                "historical_wind": hist_wind_prov,
                "historical_currents": hist_curr_prov,
                "forecast_wind": fc_wind_prov,
                "forecast_currents": fc_curr_prov,
            }
        )

        # 3.3 Origin Summary
        best_cand_summary = None
        cand_summaries = []
        if origin_res.best_candidate:
            bc = origin_res.best_candidate
            hours_b_t0 = (obs_time_utc - bc.release_time).total_seconds() / 3600.0
            unc = OriginUncertaintySummary(
                spread_radius_km=bc.uncertainty_radius_km,
                semi_major_axis_km=bc.semi_major_axis_km,
                semi_minor_axis_km=bc.semi_minor_axis_km,
                orientation_deg=bc.orientation_deg,
            )
            best_cand_summary = OriginCandidateSummary(
                candidate_id=bc.candidate_id,
                centroid=LatLonCoord(lat=bc.latitude, lon=bc.longitude),
                evidence_score=bc.candidate_score,
                release_time_utc=bc.release_time,
                hours_before_t0=round(hours_b_t0, 2),
                uncertainty=unc,
                active_particles=bc.active_particle_count,
            )

        for c in origin_res.candidates:
            h_b_t0 = (obs_time_utc - c.release_time).total_seconds() / 3600.0
            c_unc = OriginUncertaintySummary(
                spread_radius_km=c.uncertainty_radius_km,
                semi_major_axis_km=c.semi_major_axis_km,
                semi_minor_axis_km=c.semi_minor_axis_km,
                orientation_deg=c.orientation_deg,
            )
            cand_summaries.append(OriginCandidateSummary(
                candidate_id=c.candidate_id,
                centroid=LatLonCoord(lat=c.latitude, lon=c.longitude),
                evidence_score=c.candidate_score,
                release_time_utc=c.release_time,
                hours_before_t0=round(h_b_t0, 2),
                uncertainty=c_unc,
                active_particles=c.active_particle_count,
            ))

        origin_summary = OriginOutputSummary(
            best_candidate=best_cand_summary,
            evidence_score=best_cand_summary.evidence_score if best_cand_summary else None,
            release_time_window=origin_res.release_time_window,
            candidate_count=len(origin_res.candidates),
            uncertainty=best_cand_summary.uncertainty if best_cand_summary else None,
            candidates=cand_summaries,
            search_horizon_hours=origin_res.search_horizon_hours,
        )

        # 3.4 Forecast Horizons Summary (+6h, +12h, +24h, +48h)
        fc_horizons_list = []
        min_active_frac = 1.0
        coverage_warnings = []

        for h_key in ["6h", "12h", "24h", "48h"]:
            if h_key in forecast_res.forecast:
                fch = forecast_res.forecast[h_key]
                min_active_frac = min(min_active_frac, fch.active_fraction)
                if not fch.valid:
                    coverage_warnings.append(f"Forecast horizon +{h_key} marked degraded/invalid: {fch.reason or 'boundary limit'}")
                fc_horizons_list.append(ForecastHorizonSummary(
                    horizon_hours=fch.lead_time_hours,
                    timestamp=fch.forecast_time,
                    centroid=LatLonCoord(lat=fch.centroid.latitude, lon=fch.centroid.longitude),
                    active_particles=fch.active_particle_count,
                    total_particles=fch.total_particle_count,
                    spread_radius_km=round(fch.uncertainty.radius_km, 3),
                    uncertainty=fch.uncertainty,
                    simulation_quality=fch.quality.upper(),
                    quality=fch.quality.upper(),
                    valid=fch.valid,
                    predicted_slick_polygon=fch.predicted_slick_polygon,
                ))

        forecast_summary = ForecastOutputSummary(
            initialization=ForecastInitializationSummary(
                source="observed_feature1_slick",
                time=obs_time_utc,
                centroid=LatLonCoord(lat=slick.centroid.latitude, lon=slick.centroid.longitude),
            ),
            horizons=fc_horizons_list,
            ensemble=ForecastEnsembleSummary(
                ensemble_realizations=self.settings.forecast.forecast_ensemble_size,
                particles_per_realization=self.settings.forecast.particles_per_slick,
                total_particles=self.settings.forecast.forecast_ensemble_size * self.settings.forecast.particles_per_slick,
                particles_per_slick=self.settings.forecast.particles_per_slick,
                horizontal_diffusivity_m2_s=self.settings.diffusion.horizontal_diffusivity_m2_s,
                ensemble_classification="stochastic_particle_realization",
                dispersion_interpretation="Spatial dispersion bounds represent numerical sub-grid turbulent diffusion spread, not a calibrated statistical confidence interval.",
            ),
        )

        # 3.5 Quality Evaluation
        if min_active_frac < 0.8:
            coverage_warnings.append(f"Particle retention dropped to {min_active_frac * 100:.1f}% over forecast duration.")

        overall_quality = "HIGH"
        if min_active_frac < 0.4 or len(coverage_warnings) >= 2 or not origin_res.best_candidate:
            overall_quality = "LOW"
        elif min_active_frac < 0.8 or len(coverage_warnings) >= 1:
            overall_quality = "MEDIUM"

        quality_summary = QualityAssessmentSummary(
            overall_simulation_quality=overall_quality,
            overall=overall_quality,
            quality_metric_type="numerical_simulation_integrity",
            accuracy_notice="The 'HIGH' quality rating reflects numerical simulation integrity (active particle retention and environmental domain coverage). It is NOT an empirical forecast accuracy estimate.",
            historical_data_complete=True,
            forecast_data_complete=True,
            particle_retention_ratio=round(min_active_frac, 4),
            coverage_warnings=coverage_warnings,
        )

        # 3.6 Reproducibility
        reproducibility_summary = ReproducibilitySummary(
            random_seed=self.settings.random_seed,
            ensemble_size=self.settings.forecast.forecast_ensemble_size,
            particles_per_slick=self.settings.forecast.particles_per_slick,
            simulation_step_seconds=self.settings.forecast.simulation_step_seconds,
            configuration_hash=self.settings.get_reproducibility_hash(),
            feature2_version="1.0.0",
        )

        # 4. Consolidated response
        return Feature2PipelineResponse(
            feature2_version="1.0.0",
            spill_id=slick.spill_id,
            observation_time=obs_time_utc,
            origin_estimation=origin_res.origin_estimation,
            origin_analysis=origin_res,
            forecast=forecast_res.forecast,
            forecast_analysis=forecast_res,
            disclaimers=origin_res.disclaimers,
            observation=observation_summary,
            environment=environment_summary,
            origin=origin_summary,
            forecast_summary=forecast_summary,
            quality=quality_summary,
            reproducibility=reproducibility_summary,
        )
