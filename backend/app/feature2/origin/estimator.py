"""
Master origin candidate estimation pipeline (Task 3D).
Converts backward reconstructed particle states into ranked origin candidates using:
  1. Backward Lagrangian trajectory reconstruction (Task 3C)
  2. Local metric spatial clustering (metric DBSCAN)
  3. Spatial convergence / compactness scoring
  4. Trajectory continuity and environmental coverage scoring
  5. Explainable relative candidate scoring and release window selection
"""

from datetime import datetime, timedelta, timezone
import math
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import numpy as np

from ..schemas.input_schema import SlickDetectionInput, CentroidCoordinates
from ..schemas.output_schema import (
    OriginCandidate,
    OriginEstimationResult,
    ReleaseTimeWindowRange,
    ScientificDisclaimers,
)
from ..schemas.simulation_schema import (
    Particle,
    ParticleState,
    ParticleEnsemble,
    BackwardCandidateState,
)
from ..data.base import EnvironmentalDataProvider
from ..data.domain import SentinelObservationDomain, EnvironmentalQueryDomain
from ..data.time_utils import normalize_to_utc
from ..geo.coordinates import haversine_distance_km
from ..config import Feature2Settings, default_settings
from ..simulation.backward.engine import BackwardSimulationEngine, generate_candidate_release_times
from .convergence.cluster import ConvergenceClusterer
from .scoring.confidence import OriginConfidenceScorer
from .scoring.timeline import ReleaseTimelineEstimator
from ..logging_config import logger


class OriginEstimator:
    """
    End-to-end origin candidate generation and convergence scoring engine.
    Produces ranked origin candidates with spatial uncertainty, evidence scores,
    and plausible historical release time windows.
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
        self.backward_engine = BackwardSimulationEngine(
            currents_provider=self.currents_provider,
            wind_provider=self.wind_provider,
            settings=self.settings
        )
        self.clusterer = ConvergenceClusterer(self.settings.backward)
        self.scorer = OriginConfidenceScorer(self.settings.backward)
        self.timeline_estimator = ReleaseTimelineEstimator(self.settings.backward)

    def estimate_origins(
        self,
        source: Union[SlickDetectionInput, SentinelObservationDomain, List[Particle], ParticleEnsemble],
        observation_time: Optional[Union[datetime, str]] = None,
        spill_id: Optional[str] = None,
        max_backtrack_hours: Optional[float] = None,
        candidate_interval_hours: Optional[float] = None,
        dt_seconds: Optional[float] = None,
        windage_fraction: Optional[float] = None,
        query_domain: Optional[EnvironmentalQueryDomain] = None,
    ) -> OriginEstimationResult:
        """
        Executes backward reconstruction across candidate release times, clusters endpoints,
        and computes ranked origin candidates.

        Args:
            source: SlickDetectionInput, SentinelObservationDomain, or initial particle ensemble.
            observation_time: Observation timestamp T0 (UTC).
            spill_id: Identifier for the spill event.
            max_backtrack_hours: Maximum historical search horizon in hours.
            candidate_interval_hours: Historical evaluation interval in hours.
            dt_seconds: Integration timestep in seconds.
            windage_fraction: Leeway factor for surface windage.
            query_domain: Optional environmental domain.

        Returns:
            OriginEstimationResult with ranked candidates and plausible release window.
        """
        eff_spill_id = spill_id or getattr(source, "spill_id", "SPILL_UNKNOWN")
        horizon_h = (
            max_backtrack_hours if max_backtrack_hours is not None
            else self.settings.backward.max_backtrack_hours
        )
        interval_h = (
            candidate_interval_hours if candidate_interval_hours is not None
            else self.settings.backward.candidate_time_step_hours
        )
        step_dt = (
            dt_seconds if dt_seconds is not None
            else float(self.settings.backward.simulation_step_seconds)
        )

        # 1. Execute backward candidate evaluations
        candidate_eval = self.backward_engine.evaluate_backward_candidates(
            source=source,
            observation_time=observation_time,
            max_backtrack_hours=horizon_h,
            candidate_interval_hours=interval_h,
            dt_seconds=step_dt,
            windage_fraction=windage_fraction,
            query_domain=query_domain
        )

        sim_t0 = candidate_eval.observation_time
        extracted_candidates: List[OriginCandidate] = []
        raw_idx = 0

        # 2. Extract clusters and compute multi-component evidence scores per candidate release state
        for cand_state in candidate_eval.candidates:
            if cand_state.active_particle_count == 0:
                logger.info(
                    f"Candidate state at {cand_state.candidate_release_time.isoformat()} "
                    "has 0 active particles (all deactivated); skipping candidate generation."
                )
                continue

            # Cluster active particles using metric DBSCAN
            clusters = self.clusterer.cluster_particles(cand_state.reconstructed_particles)

            for cl in clusters:
                raw_idx += 1
                s_conv = self.scorer.compute_convergence_score(
                    spread_radius_km=cl["uncertainty_radius_km"]
                )
                s_traj = self.scorer.compute_trajectory_score(
                    active_particle_count=cl["active_count"],
                    total_particle_count=cand_state.total_particle_count,
                    cluster_fraction=cl["cluster_fraction"]
                )
                s_cov = self.scorer.compute_coverage_score(
                    active_particle_count=cand_state.active_particle_count,
                    total_particle_count=cand_state.total_particle_count
                )
                c_score = self.scorer.calculate_candidate_score(
                    convergence_score=s_conv,
                    trajectory_score=s_traj,
                    coverage_score=s_cov
                )

                candidate = OriginCandidate(
                    candidate_id=f"ORIGIN_{raw_idx}",
                    cluster_id=cl["cluster_id"],
                    release_time=cand_state.candidate_release_time,
                    latitude=round(cl["centroid_latitude"], 6),
                    longitude=round(cl["centroid_longitude"], 6),
                    candidate_score=round(c_score, 4),
                    convergence_score=round(s_conv, 4),
                    trajectory_score=round(s_traj, 4),
                    coverage_score=round(s_cov, 4),
                    uncertainty_radius_km=cl["uncertainty_radius_km"],
                    active_particle_count=cl["active_count"],
                    total_particle_count=cand_state.total_particle_count,
                    cluster_fraction=round(cl["cluster_fraction"], 4),
                    covariance_matrix=cl["covariance_matrix_m2"],
                    semi_major_axis_km=cl["semi_major_axis_km"],
                    semi_minor_axis_km=cl["semi_minor_axis_km"],
                    orientation_deg=cl["orientation_deg"],
                    metadata={
                        "backward_duration_hours": cand_state.backward_duration_hours,
                        "spread_radius_m": round(cl["spread_radius_m"], 2),
                    }
                )
                extracted_candidates.append(candidate)

        # 3. Optional duplicate merging across adjacent release times
        merged_candidates = self._merge_near_duplicate_candidates(extracted_candidates)

        # 4. Rank candidates descending by candidate_score
        merged_candidates.sort(key=lambda c: c.candidate_score, reverse=True)

        # Re-index clean candidate IDs (ORIGIN_1, ORIGIN_2, ...)
        for rank_idx, cand in enumerate(merged_candidates, start=1):
            cand.candidate_id = f"ORIGIN_{rank_idx}"

        best_cand = merged_candidates[0] if merged_candidates else None

        # 5. Estimate plausible historical release time window
        release_window = self.timeline_estimator.estimate_candidate_window(
            ranked_candidates=merged_candidates,
            relative_score_threshold=self.settings.backward.relative_score_threshold
        )

        return OriginEstimationResult(
            spill_id=eff_spill_id,
            observation_time=sim_t0,
            search_horizon_hours=horizon_h,
            best_candidate=best_cand,
            candidates=merged_candidates,
            release_time_window=release_window,
            disclaimers=ScientificDisclaimers()
        )

    def _merge_near_duplicate_candidates(
        self,
        candidates: List[OriginCandidate]
    ) -> List[OriginCandidate]:
        """
        Merges near-duplicate candidates that are within merge_radius_km and merge_time_hours,
        preserving distinct temporal hypotheses while avoiding redundant clusters.
        """
        merge_dist_km = self.settings.backward.merge_radius_km
        merge_time_h = self.settings.backward.merge_time_hours

        if merge_dist_km <= 0.0 or merge_time_h <= 0.0 or len(candidates) <= 1:
            return candidates

        sorted_by_score = sorted(candidates, key=lambda c: c.candidate_score, reverse=True)
        retained: List[OriginCandidate] = []

        for cand in sorted_by_score:
            is_dup = False
            for ret in retained:
                time_diff_h = abs((cand.release_time - ret.release_time).total_seconds()) / 3600.0
                if time_diff_h <= merge_time_h:
                    dist_km = haversine_distance_km(
                        cand.latitude, cand.longitude,
                        ret.latitude, ret.longitude
                    )
                    if dist_km <= merge_dist_km:
                        is_dup = True
                        break
            if not is_dup:
                retained.append(cand)

        return retained


def estimate_origin_candidates(
    source: Union[SlickDetectionInput, SentinelObservationDomain, List[Particle], ParticleEnsemble],
    current_provider: EnvironmentalDataProvider,
    wind_provider: Optional[EnvironmentalDataProvider] = None,
    observation_time: Optional[Union[datetime, str]] = None,
    spill_id: Optional[str] = None,
    max_backtrack_hours: Optional[float] = None,
    candidate_interval_hours: Optional[float] = None,
    dt_seconds: Optional[float] = None,
    windage_fraction: Optional[float] = None,
    config: Optional[Feature2Settings] = None,
    query_domain: Optional[EnvironmentalQueryDomain] = None,
) -> OriginEstimationResult:
    """
    Convenience functional interface for origin candidate estimation and convergence scoring.
    """
    estimator = OriginEstimator(
        currents_provider=current_provider,
        wind_provider=wind_provider,
        settings=config or default_settings
    )

    return estimator.estimate_origins(
        source=source,
        observation_time=observation_time,
        spill_id=spill_id,
        max_backtrack_hours=max_backtrack_hours,
        candidate_interval_hours=candidate_interval_hours,
        dt_seconds=dt_seconds,
        windage_fraction=windage_fraction,
        query_domain=query_domain
    )
