"""
FastAPI REST endpoints for Feature 2:
1. /health
2. /trace-origin (Backward inverse reconstruction)
3. /forecast (Forward slick trajectory prediction)
4. /pipeline (Consolidated full pipeline)
5. /geojson/origin, /geojson/forecast, /geojson/pipeline (Map-ready GeoJSON FeatureCollections)
6. /pipeline/unified (Unified Feature 2 Result contract)
"""

from typing import Any, Dict, Union
from fastapi import APIRouter, Depends, HTTPException, status
from ..schemas.input_schema import SlickDetectionInput
from ..schemas.feature1_adapter import parse_feature1_input
from ..schemas.output_schema import (
    OriginAnalysisResult,
    ForecastAnalysisResult,
    Feature2PipelineResponse,
    UnifiedFeature2Result,
    ScientificDisclaimers,
)
from ..pipeline.service import Feature2PipelineService
from ..output.formatter import OutputFormatter
from .dependencies import get_pipeline_service
from ..exceptions import EnvironmentalDataError, EnvironmentalCoverageError, InvalidInputGeometryError
from ..logging_config import logger

router = APIRouter(prefix="/feature2", tags=["Feature 2 - Oil Spill Tracing & Forecasting"])


def _normalize_input(payload: Union[SlickDetectionInput, Dict[str, Any]]) -> SlickDetectionInput:
    """Normalizes Feature 1 input payload from either GeoJSON FeatureCollection or internal schema."""
    try:
        return parse_feature1_input(payload)
    except (InvalidInputGeometryError, ValueError) as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid Feature 1 input geometry or schema: {err}"
        ) from err


@router.get("/health", summary="Feature 2 Health Check")
async def health_check():
    """Health check endpoint for Feature 2 service."""
    return {"status": "healthy", "module": "feature2", "version": "0.1.0"}


@router.post(
    "/trace-origin",
    response_model=OriginAnalysisResult,
    summary="Inverse Slick Origin Tracing"
)
async def trace_spill_origin(
    payload: Union[SlickDetectionInput, Dict[str, Any]],
    service: Feature2PipelineService = Depends(get_pipeline_service),
):
    """
    Takes observed SAR slick from Feature 1 (GeoJSON FeatureCollection or internal model)
    and performs backward trajectory reconstruction across candidate release windows before T0.
    """
    slick = _normalize_input(payload)
    logger.info(f"Origin trace requested for spill: {slick.spill_id}")
    try:
        return service.trace_origin(slick)
    except EnvironmentalDataError as e:
        logger.error(f"Environmental data failure during origin trace for {slick.spill_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Environmental data coverage error: {str(e)}"
        )


@router.post(
    "/forecast",
    response_model=ForecastAnalysisResult,
    summary="Forward Slick Trajectory Forecasting"
)
async def forecast_slick(
    payload: Union[SlickDetectionInput, Dict[str, Any]],
    service: Feature2PipelineService = Depends(get_pipeline_service),
):
    """
    Simulates forward slick movement from observation time T0 across configured
    horizons (+6h, +12h, +24h, +48h).
    """
    slick = _normalize_input(payload)
    logger.info(f"Forecast requested for spill: {slick.spill_id}")
    try:
        return service.predict_forecast(slick)
    except EnvironmentalDataError as e:
        logger.error(f"Environmental data failure during forecast for {slick.spill_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Environmental data coverage error: {str(e)}"
        )


@router.post(
    "/pipeline",
    response_model=Feature2PipelineResponse,
    summary="Execute Full Feature 2 Pipeline"
)
async def run_full_pipeline(
    payload: Union[SlickDetectionInput, Dict[str, Any]],
    service: Feature2PipelineService = Depends(get_pipeline_service),
):
    """
    Runs both backward inverse reconstruction and forward forecasting in a single call.
    """
    slick = _normalize_input(payload)
    logger.info(f"Full pipeline requested for spill: {slick.spill_id}")
    try:
        return service.run_pipeline(slick)
    except EnvironmentalDataError as e:
        logger.error(f"Environmental data failure during pipeline for {slick.spill_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Environmental data coverage error: {str(e)}"
        )


@router.post(
    "/pipeline/unified",
    response_model=UnifiedFeature2Result,
    summary="Execute Full Feature 2 Pipeline with Unified Result Contract"
)
async def run_pipeline_unified(
    payload: Union[SlickDetectionInput, Dict[str, Any]],
    service: Feature2PipelineService = Depends(get_pipeline_service),
):
    """
    Runs both backward origin reconstruction and forward forecasting,
    returning the unified, audit-ready Feature 2 contract.
    """
    slick = _normalize_input(payload)
    logger.info(f"Unified pipeline requested for spill: {slick.spill_id}")
    try:
        pipeline_res = service.run_pipeline(slick)
        return pipeline_res.to_unified_result()
    except EnvironmentalDataError as e:
        logger.error(f"Environmental data failure during unified pipeline for {slick.spill_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Environmental data coverage error: {str(e)}"
        )


@router.post(
    "/geojson/origin",
    response_model=Dict[str, Any],
    summary="Origin Tracing GeoJSON FeatureCollection"
)
async def origin_geojson(
    payload: Union[SlickDetectionInput, Dict[str, Any]],
    service: Feature2PipelineService = Depends(get_pipeline_service),
):
    """Returns candidate origin centroids and dispersion uncertainty ellipses as RFC 7946 GeoJSON."""
    slick = _normalize_input(payload)
    try:
        origin_res = service.trace_origin(slick)
        return OutputFormatter.origin_result_to_geojson(origin_res)
    except EnvironmentalDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Environmental data coverage error: {str(e)}"
        )


@router.post(
    "/geojson/forecast",
    response_model=Dict[str, Any],
    summary="Forecast Horizons GeoJSON FeatureCollection"
)
async def forecast_geojson(
    payload: Union[SlickDetectionInput, Dict[str, Any]],
    service: Feature2PipelineService = Depends(get_pipeline_service),
):
    """Returns forward predicted slick centroids and uncertainty zones as RFC 7946 GeoJSON."""
    slick = _normalize_input(payload)
    try:
        forecast_res = service.predict_forecast(slick)
        return OutputFormatter.forecast_result_to_geojson(forecast_res)
    except EnvironmentalDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Environmental data coverage error: {str(e)}"
        )


@router.post(
    "/geojson/pipeline",
    response_model=Dict[str, Any],
    summary="Complete Feature 2 Pipeline GeoJSON FeatureCollection"
)
async def pipeline_geojson(
    payload: Union[SlickDetectionInput, Dict[str, Any]],
    service: Feature2PipelineService = Depends(get_pipeline_service),
):
    """Returns combined origin and forecast features in a single GeoJSON FeatureCollection."""
    slick = _normalize_input(payload)
    try:
        pipeline_res = service.run_pipeline(slick)
        return OutputFormatter.pipeline_result_to_geojson(pipeline_res)
    except EnvironmentalDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Environmental data coverage error: {str(e)}"
        )


@router.post(
    "/geojson/observation",
    response_model=Dict[str, Any],
    summary="Observed Slick GeoJSON FeatureCollection"
)
async def observation_geojson(
    payload: Union[SlickDetectionInput, Dict[str, Any]],
):
    """Returns observed Feature 1 slick polygon boundary and centroid as RFC 7946 GeoJSON."""
    slick = _normalize_input(payload)
    return OutputFormatter.observed_slick_to_geojson(slick)
