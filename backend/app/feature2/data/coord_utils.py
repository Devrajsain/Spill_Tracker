"""
Coordinate convention normalization and grid search utilities.
Supports [-180, 180] and [0, 360] longitude domains and ascending/descending latitude axes.
"""

from typing import Literal, Tuple
import numpy as np


def normalize_longitude(
    lon: float,
    convention: Literal["[-180, 180]", "[0, 360]"] = "[-180, 180]"
) -> float:
    """
    Normalizes a longitude value to the target convention.
    
    Conventions:
      - "[-180, 180]": range is [-180.0, 180.0]
      - "[0, 360]":    range is [0.0, 360.0]
    """
    if convention == "[-180, 180]":
        if -180.0 <= lon <= 180.0:
            return float(lon)
        norm = ((lon + 180.0) % 360.0) - 180.0
        if norm == -180.0 and lon > 0:
            return 180.0
        return float(round(norm, 10))
    elif convention == "[0, 360]":
        if 0.0 <= lon < 360.0:
            return float(lon)
        if lon == 360.0:
            return 360.0
        norm = lon % 360.0
        return float(round(norm, 10))
    else:
        raise ValueError(f"Unknown longitude convention: {convention}. Must be '[-180, 180]' or '[0, 360]'.")


def detect_longitude_convention(lons: np.ndarray) -> Literal["[-180, 180]", "[0, 360]"]:
    """
    Detects whether a 1D longitude array follows [-180, 180] or [0, 360].
    """
    min_lon = float(np.min(lons))
    max_lon = float(np.max(lons))
    if min_lon < 0.0:
        return "[-180, 180]"
    if max_lon > 180.0:
        return "[0, 360]"
    return "[-180, 180]"


def find_grid_bounding_indices(
    grid_coords: np.ndarray,
    target_val: float
) -> Tuple[int, int, float]:
    """
    Finds bounding indices (i0, i1) and linear interpolation fraction weight t in [0, 1]
    such that target_val lies between grid_coords[i0] and grid_coords[i1].
    
    Handles both strictly ascending and strictly descending 1D coordinate arrays.
    
    Returns:
        (i0, i1, fraction_weight) where:
          interpolated_value = (1 - t) * grid[i0] + t * grid[i1]
    """
    if len(grid_coords) < 2:
        raise ValueError(f"Grid coordinate array must have at least 2 points, got {len(grid_coords)}")

    is_ascending = grid_coords[0] < grid_coords[-1]
    min_val = float(grid_coords[0] if is_ascending else grid_coords[-1])
    max_val = float(grid_coords[-1] if is_ascending else grid_coords[0])

    tol = 1e-7
    if target_val < min_val - tol or target_val > max_val + tol:
        raise ValueError(
            f"Target value {target_val} is outside coordinate domain [{min_val}, {max_val}]"
        )

    target_val = min(max(target_val, min_val), max_val)

    if is_ascending:
        idx = int(np.searchsorted(grid_coords, target_val, side="right"))
        if idx == 0:
            i0, i1 = 0, 1
        elif idx >= len(grid_coords):
            i0, i1 = len(grid_coords) - 2, len(grid_coords) - 1
        else:
            i0, i1 = idx - 1, idx
    else:
        rev_coords = grid_coords[::-1]
        rev_idx = int(np.searchsorted(rev_coords, target_val, side="right"))
        if rev_idx == 0:
            rev_i0, rev_i1 = 0, 1
        elif rev_idx >= len(rev_coords):
            rev_i0, rev_i1 = len(rev_coords) - 2, len(rev_coords) - 1
        else:
            rev_i0, rev_i1 = rev_idx - 1, rev_idx
        n = len(grid_coords)
        i0 = n - 1 - rev_i0
        i1 = n - 1 - rev_i1
        if i0 > i1:
            i0, i1 = i1, i0

    val0 = float(grid_coords[i0])
    val1 = float(grid_coords[i1])
    denom = val1 - val0

    if abs(denom) < 1e-12:
        t = 0.0
    else:
        t = (target_val - val0) / denom

    t = min(max(t, 0.0), 1.0)
    return i0, i1, float(t)
