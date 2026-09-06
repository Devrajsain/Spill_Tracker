"""
GeoJSON formatting utilities for Feature 2 outputs.
Converts observed slicks, candidate origin zones, predicted future slicks,
and uncertainty ellipses into standard RFC 7946 GeoJSON FeatureCollections.
"""

from typing import Any, Dict, List, Optional
from ..schemas.output_schema import (
    OriginAnalysisResult,
    ForecastAnalysisResult,
    Feature2PipelineResponse,
    UnifiedFeature2Result,
    CandidateOrigin,
    ForecastStepResult
)


class OutputFormatter:
    """Formats simulation and analytical outputs into standard GeoJSON FeatureCollections."""

    @staticmethod
    def observed_slick_to_geojson(slick: Any) -> Dict[str, Any]:
        """Converts Feature 1 observed slick geometry and centroid to a GeoJSON FeatureCollection."""
        features: List[Dict[str, Any]] = []

        spill_id = getattr(slick, "spill_id", "UNKNOWN_SPILL")
        obs_time = getattr(slick, "observation_time", None)
        obs_time_str = obs_time.isoformat() if hasattr(obs_time, "isoformat") else str(obs_time)

        # 1. Observed Slick Polygon Boundary
        geometry = getattr(slick, "geometry", None)
        if geometry:
            geom_dict = geometry.model_dump() if hasattr(geometry, "model_dump") else (
                geometry.dict() if hasattr(geometry, "dict") else geometry
            )
            features.append({
                "type": "Feature",
                "properties": {
                    "feature_type": "observed_slick_polygon",
                    "spill_id": spill_id,
                    "observation_time": obs_time_str,
                    "area_km2": getattr(slick, "area_sq_km", getattr(slick, "area_km2", None)),
                    "perimeter_km": getattr(slick, "perimeter_km", None),
                    "source": "Feature 1 Sentinel-1 SAR Detection",
                },
                "geometry": geom_dict
            })

        # 2. Observed Slick Centroid
        centroid = getattr(slick, "centroid", None)
        if centroid:
            c_lat = getattr(centroid, "latitude", getattr(centroid, "lat", None))
            c_lon = getattr(centroid, "longitude", getattr(centroid, "lon", None))
            if c_lat is not None and c_lon is not None:
                features.append({
                    "type": "Feature",
                    "properties": {
                        "feature_type": "observed_slick_centroid",
                        "spill_id": spill_id,
                        "observation_time": obs_time_str,
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [c_lon, c_lat]
                    }
                })

        return {
            "type": "FeatureCollection",
            "features": features
        }

    @staticmethod
    def origin_result_to_geojson(result: OriginAnalysisResult) -> Dict[str, Any]:
        """Converts origin candidate clusters and uncertainty polygons to GeoJSON."""
        features: List[Dict[str, Any]] = []

        obs_time_str = result.observation_time.isoformat() if hasattr(result.observation_time, "isoformat") else str(result.observation_time)

        for rank_idx, candidate in enumerate(result.candidate_origins):
            score = getattr(candidate, "evidence_score", candidate.confidence_score)
            rel_start = candidate.release_time_window.earliest_utc.isoformat()
            rel_end = candidate.release_time_window.latest_utc.isoformat()
            spread_km = candidate.spatial_uncertainty.semi_major_axis_km

            # Add centroid point feature
            features.append({
                "type": "Feature",
                "properties": {
                    "feature_type": "candidate_origin_centroid",
                    "spill_id": result.spill_id,
                    "candidate_rank": rank_idx + 1,
                    "cluster_id": candidate.cluster_id,
                    "evidence_score": score,
                    "confidence_score": candidate.confidence_score,
                    "observation_time": obs_time_str,
                    "particle_support_ratio": candidate.particle_support_ratio,
                    "peak_evidence_time": candidate.release_time_window.peak_evidence_utc.isoformat(),
                    "release_window_start": rel_start,
                    "release_window_end": rel_end,
                    "spread_radius_km": spread_km,
                    "disclaimer": "The origin score is a normalized evidence/confidence metric and is not a calibrated probability. The candidate region is an estimated convergence zone, not a confirmed spill source.",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [candidate.estimated_centroid.longitude, candidate.estimated_centroid.latitude]
                }
            })

            # Add spatial uncertainty polygon feature
            features.append({
                "type": "Feature",
                "properties": {
                    "feature_type": "candidate_origin_uncertainty_zone",
                    "spill_id": result.spill_id,
                    "candidate_rank": rank_idx + 1,
                    "cluster_id": candidate.cluster_id,
                    "evidence_score": score,
                    "semi_major_axis_km": candidate.spatial_uncertainty.semi_major_axis_km,
                    "semi_minor_axis_km": candidate.spatial_uncertainty.semi_minor_axis_km,
                    "spread_radius_km": spread_km,
                    "disclaimer": "Statistical dispersion ellipse representing spatial uncertainty, not a calibrated 95% probability boundary.",
                },
                "geometry": candidate.spatial_uncertainty.uncertainty_polygon.model_dump()
            })

        return {
            "type": "FeatureCollection",
            "features": features
        }

    @staticmethod
    def forecast_result_to_geojson(result: ForecastAnalysisResult) -> Dict[str, Any]:
        """Converts forward forecast horizons (+6h, +12h, +24h, +48h) to GeoJSON FeatureCollection."""
        features: List[Dict[str, Any]] = []

        # If horizon-keyed dict is available, use it for richer metadata
        if result.forecast:
            for key, horizon in result.forecast.items():
                fc_time_str = horizon.forecast_time.isoformat() if hasattr(horizon.forecast_time, "isoformat") else str(horizon.forecast_time)

                # 1. Forecast predicted centroid point
                features.append({
                    "type": "Feature",
                    "properties": {
                        "feature_type": "forecast_predicted_centroid",
                        "spill_id": result.spill_id,
                        "horizon_hours": horizon.lead_time_hours,
                        "forecast_timestamp": fc_time_str,
                        "forecast_time_utc": fc_time_str,
                        "centroid": {"lat": horizon.centroid.latitude, "lon": horizon.centroid.longitude},
                        "spread_radius_km": horizon.uncertainty.radius_km,
                        "valid": horizon.valid,
                        "quality": horizon.quality.upper(),
                        "active_fraction": horizon.active_fraction,
                        "active_particles": horizon.active_particle_count,
                        "total_particles": horizon.total_particle_count,
                        "mean_drift_speed_kmh": horizon.mean_drift_speed_kmh,
                        "mean_drift_direction_deg": horizon.mean_drift_direction_deg,
                        "uncertainty_radius_km": horizon.uncertainty.radius_km,
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [horizon.centroid.longitude, horizon.centroid.latitude]
                    }
                })

                # 2. Forecast covariance uncertainty boundary
                if horizon.uncertainty.uncertainty_polygon is not None:
                    features.append({
                        "type": "Feature",
                        "properties": {
                            "feature_type": "forecast_uncertainty_zone",
                            "polygon_type": "modeled_dispersion_envelope",
                            "spill_id": result.spill_id,
                            "horizon_hours": horizon.lead_time_hours,
                            "forecast_timestamp": fc_time_str,
                            "lead_time_hours": horizon.lead_time_hours,
                            "semi_major_axis_km": horizon.uncertainty.semi_major_km,
                            "semi_minor_axis_km": horizon.uncertainty.semi_minor_km,
                            "orientation_deg": horizon.uncertainty.orientation_deg,
                            "spread_radius_km": horizon.uncertainty.radius_km,
                            "uncertainty_radius_km": horizon.uncertainty.radius_km,
                            "quality": horizon.quality.upper(),
                            "disclaimer": "Modeled spatial dispersion envelope representing particle spread uncertainty, not physical slick boundary or emulsion morphology.",
                        },
                        "geometry": horizon.uncertainty.uncertainty_polygon.model_dump()
                    })
        else:
            for horizon in result.horizons:
                fc_time_str = horizon.forecast_time_utc.isoformat() if hasattr(horizon.forecast_time_utc, "isoformat") else str(horizon.forecast_time_utc)
                features.append({
                    "type": "Feature",
                    "properties": {
                        "feature_type": "forecast_predicted_centroid",
                        "spill_id": result.spill_id,
                        "horizon_hours": horizon.lead_time_hours,
                        "forecast_timestamp": fc_time_str,
                        "lead_time_hours": horizon.lead_time_hours,
                        "forecast_time_utc": fc_time_str,
                        "centroid": {"lat": horizon.predicted_centroid.latitude, "lon": horizon.predicted_centroid.longitude},
                        "spread_radius_km": horizon.spatial_uncertainty.semi_major_axis_km,
                        "mean_drift_speed_kmh": horizon.mean_drift_speed_kmh,
                        "mean_drift_direction_deg": horizon.mean_drift_direction_deg,
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [horizon.predicted_centroid.longitude, horizon.predicted_centroid.latitude]
                    }
                })

                features.append({
                    "type": "Feature",
                    "properties": {
                        "feature_type": "forecast_uncertainty_zone",
                        "polygon_type": "modeled_dispersion_envelope",
                        "spill_id": result.spill_id,
                        "horizon_hours": horizon.lead_time_hours,
                        "forecast_timestamp": fc_time_str,
                        "lead_time_hours": horizon.lead_time_hours,
                        "semi_major_axis_km": horizon.spatial_uncertainty.semi_major_axis_km,
                        "semi_minor_axis_km": horizon.spatial_uncertainty.semi_minor_axis_km,
                        "spread_radius_km": horizon.spatial_uncertainty.semi_major_axis_km,
                        "disclaimer": "Modeled spatial dispersion envelope representing particle spread uncertainty, not physical slick boundary or emulsion morphology.",
                    },
                    "geometry": horizon.spatial_uncertainty.uncertainty_polygon.model_dump()
                })

        return {
            "type": "FeatureCollection",
            "features": features
        }

    @classmethod
    def pipeline_result_to_geojson(cls, result: Feature2PipelineResponse) -> Dict[str, Any]:
        """Combines observed slick, origin candidate zones, and forecast horizons into a single GeoJSON FeatureCollection."""
        combined_features: List[Dict[str, Any]] = []

        # 1. Include observed slick if available in unified observation section
        if result.observation is not None:
            obs_dict = {
                "spill_id": result.spill_id,
                "observation_time": result.observation.observation_time,
                "centroid": result.observation.centroid,
                "geometry": result.observation.geometry,
                "area_km2": result.observation.area_km2,
            }
            obs_gj = cls.observed_slick_to_geojson(obs_dict)
            combined_features.extend(obs_gj.get("features", []))

        # 2. Origin analysis features
        if result.origin_analysis:
            origin_gj = cls.origin_result_to_geojson(result.origin_analysis)
            combined_features.extend(origin_gj.get("features", []))

        # 3. Forecast analysis features
        if result.forecast_analysis:
            forecast_gj = cls.forecast_result_to_geojson(result.forecast_analysis)
            combined_features.extend(forecast_gj.get("features", []))

        return {
            "type": "FeatureCollection",
            "features": combined_features
        }

    @classmethod
    def unified_result_to_geojson(cls, result: UnifiedFeature2Result) -> Dict[str, Any]:
        """Converts UnifiedFeature2Result into a single GeoJSON FeatureCollection."""
        combined_features: List[Dict[str, Any]] = []

        # 1. Observed Slick Features
        obs_gj = cls.observed_slick_to_geojson(result.observation)
        combined_features.extend(obs_gj.get("features", []))

        # 2. Origin Best Candidate & Clusters
        if result.origin.best_candidate is not None:
            cand = result.origin.best_candidate
            combined_features.append({
                "type": "Feature",
                "properties": {
                    "feature_type": "candidate_origin_centroid",
                    "spill_id": result.spill_id,
                    "candidate_id": cand.candidate_id,
                    "candidate_rank": 1,
                    "evidence_score": cand.evidence_score,
                    "observation_time": result.observation.observation_time.isoformat(),
                    "release_time_utc": cand.release_time_utc.isoformat(),
                    "release_window_start": result.origin.release_time_window.start.isoformat(),
                    "release_window_end": result.origin.release_time_window.end.isoformat(),
                    "spread_radius_km": cand.uncertainty.spread_radius_km,
                    "disclaimer": result.origin.disclaimer,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [cand.centroid.lon, cand.centroid.lat]
                }
            })

            if cand.uncertainty.uncertainty_polygon is not None:
                combined_features.append({
                    "type": "Feature",
                    "properties": {
                        "feature_type": "candidate_origin_uncertainty_zone",
                        "spill_id": result.spill_id,
                        "candidate_id": cand.candidate_id,
                        "candidate_rank": 1,
                        "evidence_score": cand.evidence_score,
                        "spread_radius_km": cand.uncertainty.spread_radius_km,
                        "semi_major_axis_km": cand.uncertainty.semi_major_axis_km,
                        "semi_minor_axis_km": cand.uncertainty.semi_minor_axis_km,
                    },
                    "geometry": cand.uncertainty.uncertainty_polygon.model_dump()
                })

        # 3. Forecast Horizons (+6h, +12h, +24h, +48h)
        for horizon in result.forecast.horizons:
            fc_time_str = horizon.timestamp.isoformat()
            combined_features.append({
                "type": "Feature",
                "properties": {
                    "feature_type": "forecast_predicted_centroid",
                    "spill_id": result.spill_id,
                    "horizon_hours": horizon.horizon_hours,
                    "forecast_timestamp": fc_time_str,
                    "centroid": {"lat": horizon.centroid.lat, "lon": horizon.centroid.lon},
                    "spread_radius_km": horizon.spread_radius_km,
                    "quality": horizon.quality,
                    "valid": horizon.valid,
                    "active_particles": horizon.active_particles,
                    "total_particles": horizon.total_particles,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [horizon.centroid.lon, horizon.centroid.lat]
                }
            })

            if horizon.uncertainty.uncertainty_polygon is not None:
                combined_features.append({
                    "type": "Feature",
                    "properties": {
                        "feature_type": "forecast_uncertainty_zone",
                        "spill_id": result.spill_id,
                        "horizon_hours": horizon.horizon_hours,
                        "forecast_timestamp": fc_time_str,
                        "semi_major_axis_km": horizon.uncertainty.semi_major_km,
                        "semi_minor_axis_km": horizon.uncertainty.semi_minor_km,
                        "orientation_deg": horizon.uncertainty.orientation_deg,
                        "spread_radius_km": horizon.spread_radius_km,
                        "quality": horizon.quality,
                    },
                    "geometry": horizon.uncertainty.uncertainty_polygon.model_dump()
                })

        return {
            "type": "FeatureCollection",
            "features": combined_features
        }
