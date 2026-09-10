"""
GeoTIFF Geospatial Metadata Inspection & Coordinate Transformation Service.

Inspects raster files to check for valid CRS and geotransform metadata.
Converts detected pixel coordinates (from Feature 1 spill detection)
into real-world WGS84 (EPSG:4326) latitude and longitude.
"""

import os
import logging
from typing import Dict, Any, Optional, Tuple, List
import numpy as np

logger = logging.getLogger(__name__)

# Cache availability of rasterio & pyproj
_RASTERIO_AVAILABLE = False
_PYPROJ_AVAILABLE = False

try:
    import rasterio
    from rasterio.transform import xy
    _RASTERIO_AVAILABLE = True
except Exception as e:
    logger.warning(f"rasterio not available: {e}")

try:
    import pyproj
    from pyproj import Transformer
    _PYPROJ_AVAILABLE = True
except Exception as e:
    logger.warning(f"pyproj not available: {e}")


def inspect_image_geospatial(image_path: Optional[str]) -> Dict[str, Any]:
    """
    Inspects an image file to determine if it is a GeoTIFF with valid geospatial metadata.

    Returns:
        Dict with keys:
            is_geotiff (bool): True if file has a TIFF extension and is readable by rasterio.
            has_crs (bool): True if valid, non-identity geospatial CRS and transform exist.
            crs (Optional[str]): Source CRS string (e.g. 'EPSG:4326', 'EPSG:32643').
            transform: rasterio Affine transform object if available.
            bounds: Tuple of (left, bottom, right, top) in source CRS.
            width: Image width in pixels.
            height: Image height in pixels.
            reason: Explanatory string.
    """
    result: Dict[str, Any] = {
        "is_geotiff": False,
        "has_crs": False,
        "crs": None,
        "transform": None,
        "bounds": None,
        "width": 0,
        "height": 0,
        "reason": "no_image_provided",
    }

    if not image_path or not os.path.exists(image_path):
        return result

    ext = os.path.splitext(image_path)[1].lower()
    if ext not in (".tif", ".tiff"):
        result["reason"] = "non_tiff_format"
        return result

    if not _RASTERIO_AVAILABLE or not _PYPROJ_AVAILABLE:
        result["is_geotiff"] = True
        result["reason"] = "geospatial_libraries_unavailable"
        return result

    try:
        with rasterio.open(image_path) as src:
            result["is_geotiff"] = True
            result["width"] = src.width
            result["height"] = src.height

            # Check if CRS is defined
            if src.crs is None:
                result["has_crs"] = False
                result["reason"] = "tiff_missing_crs"
                return result

            # Check if transform is merely the default unreferenced identity matrix
            # Identity transform: [1, 0, 0, 0, 1, 0]
            t = src.transform
            if t.a == 1.0 and t.b == 0.0 and t.c == 0.0 and t.d == 0.0 and t.e == 1.0 and t.f == 0.0:
                result["has_crs"] = False
                result["reason"] = "tiff_identity_transform"
                return result

            result["has_crs"] = True
            result["crs"] = str(src.crs)
            result["transform"] = t
            result["bounds"] = src.bounds
            result["reason"] = "valid_geotiff"
            return result

    except Exception as exc:
        logger.warning(f"Failed to inspect GeoTIFF metadata for {image_path}: {exc}")
        result["is_geotiff"] = True
        result["has_crs"] = False
        result["reason"] = f"read_error: {str(exc)}"
        return result


def pixel_to_wgs84(
    transform: Any,
    source_crs: Any,
    pixel_x: float,
    pixel_y: float
) -> Tuple[float, float]:
    """
    Converts a pixel coordinate (col=x, row=y) into WGS84 (latitude, longitude)
    using the raster's affine transform and projecting from source CRS to EPSG:4326.

    Returns:
        (latitude, longitude) rounded to 6 decimal places.
    """
    # rasterio.transform.xy takes (transform, row, col) -> (x, y in source CRS)
    proj_x, proj_y = xy(transform, pixel_y, pixel_x)

    crs_str = str(source_crs).upper()
    if crs_str in ("EPSG:4326", "WGS84", "OGC:CRS84"):
        # Already geographic WGS84: proj_x is longitude, proj_y is latitude
        return round(float(proj_y), 6), round(float(proj_x), 6)

    # Transform to EPSG:4326
    transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(proj_x, proj_y)
    return round(float(lat), 6), round(float(lon), 6)


def contour_to_wgs84_polygon(
    transform: Any,
    source_crs: Any,
    approx_contour: np.ndarray
) -> Dict[str, Any]:
    """
    Converts a 2D contour array of pixel coordinates into a valid GeoJSON Polygon
    with coordinates in WGS84 [longitude, latitude].
    """
    geo_coords = []
    for pt in approx_contour:
        px = float(pt[0][0])
        py = float(pt[0][1])
        lat, lon = pixel_to_wgs84(transform, source_crs, px, py)
        geo_coords.append([lon, lat])

    # Ensure polygon ring is closed
    if geo_coords and geo_coords[0] != geo_coords[-1]:
        geo_coords.append(geo_coords[0])

    return {
        "type": "Polygon",
        "coordinates": [geo_coords]
    }
