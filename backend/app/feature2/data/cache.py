"""
Caching and storage management for environmental datasets (Task 4).
Provides deterministic cache key computation, domain-aware file lookup,
atomic file writes, and data integrity verification.
"""

from datetime import datetime
import hashlib
import json
import os
import shutil
import tempfile
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import xarray as xr

from ..exceptions import EnvironmentalDataUnavailableError, InvalidDatasetError
from ..logging_config import logger


def generate_cache_key(
    provider_name: str,
    dataset_id: str,
    variables: List[str],
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    start_time_iso: str,
    end_time_iso: str,
    extra_params: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Computes a deterministic, collision-resistant cache key for a gridded environmental subset.
    Coordinates are rounded to 4 decimal places (~11m resolution) to ensure consistency.
    """
    payload = {
        "provider": provider_name.strip().lower(),
        "dataset_id": dataset_id.strip(),
        "variables": sorted([v.strip().lower() for v in variables]),
        "bbox": [
            round(min_lat, 4),
            round(max_lat, 4),
            round(min_lon, 4),
            round(max_lon, 4),
        ],
        "start_time": start_time_iso.strip().replace("+00:00", "Z"),
        "end_time": end_time_iso.strip().replace("+00:00", "Z"),
    }
    if extra_params:
        payload["extra"] = {k: str(v) for k, v in sorted(extra_params.items())}

    canonical_str = json.dumps(payload, sort_keys=True)
    hash_digest = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()[:20]
    return f"{provider_name}_{hash_digest}"


class EnvironmentalDataCacheManager:
    """
    Manages local filesystem caching of downloaded / ingested NetCDF grids.
    Ensures safe atomic file generation, domain isolation, and validation.
    """

    def __init__(self, cache_root_dir: str = "./data_cache"):
        self.cache_root_dir = os.path.abspath(cache_root_dir)
        os.makedirs(self.cache_root_dir, exist_ok=True)

    def get_provider_cache_dir(self, provider_subfolder: str) -> str:
        """Returns and ensures existence of provider-specific cache subfolder."""
        p_dir = os.path.join(self.cache_root_dir, provider_subfolder)
        os.makedirs(p_dir, exist_ok=True)
        return p_dir

    def get_cache_filepath(self, provider_subfolder: str, cache_key: str) -> str:
        """Returns destination filepath for the given cache key."""
        p_dir = self.get_provider_cache_dir(provider_subfolder)
        return os.path.join(p_dir, f"{cache_key}.nc")

    def has_valid_cache(
        self,
        provider_subfolder: str,
        cache_key: str,
        max_age_seconds: Optional[float] = None
    ) -> bool:
        """
        Checks if a valid, readable NetCDF file already exists in cache.
        Automatically deletes zero-byte or corrupt NetCDF files.
        If max_age_seconds is specified, invalidates expired cache to trigger re-fetch.
        """
        target_path = self.get_cache_filepath(provider_subfolder, cache_key)
        if not os.path.exists(target_path):
            return False

        if os.path.getsize(target_path) == 0:
            logger.warning(f"Found zero-byte corrupted cache file at '{target_path}'. Deleting.")
            try:
                os.remove(target_path)
            except Exception:
                pass
            return False

        # Ensure xarray can open headers and verify variables
        try:
            with xr.open_dataset(target_path) as ds:
                if len(ds.data_vars) == 0:
                    logger.warning(f"Cache file '{target_path}' has no data variables. Deleting.")
                    try:
                        os.remove(target_path)
                    except Exception:
                        pass
                    return False
        except Exception as e:
            logger.warning(f"Corrupted cache file detected at '{target_path}': {e}. Deleting.")
            try:
                os.remove(target_path)
            except Exception:
                pass
            return False

        # Freshness / TTL check
        if max_age_seconds is not None and max_age_seconds > 0:
            import time
            mtime = os.path.getmtime(target_path)
            age_sec = time.time() - mtime
            if age_sec > max_age_seconds:
                logger.info(
                    f"Cache EXPIRED for key '{cache_key}' (age {age_sec:.1f}s > TTL {max_age_seconds:.1f}s). "
                    "Invalidating for remote refresh."
                )
                return False

        return True

    def get_cached_file(
        self,
        provider_subfolder: str,
        cache_key: str,
        max_age_seconds: Optional[float] = None
    ) -> Optional[str]:
        """Returns filepath if valid and fresh cache exists, else None."""
        if self.has_valid_cache(provider_subfolder, cache_key, max_age_seconds=max_age_seconds):
            target_path = self.get_cache_filepath(provider_subfolder, cache_key)
            logger.info(f"Cache HIT for key '{cache_key}' at '{target_path}'")
            return target_path
        return None

    def atomic_save(
        self,
        provider_subfolder: str,
        cache_key: str,
        save_fn: Callable[[str], None]
    ) -> str:
        """
        Executes save_fn(temp_filepath) and atomically renames the temp file to destination.
        Guarantees that partially written downloads or interrupted network streams
        never corrupt the cache.
        """
        p_dir = self.get_provider_cache_dir(provider_subfolder)
        final_path = self.get_cache_filepath(provider_subfolder, cache_key)

        # Create temporary file in the exact same directory (enables atomic os.replace across filesystems)
        fd, temp_path = tempfile.mkstemp(suffix=".tmp.nc", dir=p_dir)
        os.close(fd)

        try:
            save_fn(temp_path)

            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                raise InvalidDatasetError(
                    f"Saved file '{temp_path}' is missing or 0 bytes after save_fn execution."
                )

            # Validate before committing to final cache path
            try:
                with xr.open_dataset(temp_path) as ds:
                    if len(ds.data_vars) == 0:
                        raise InvalidDatasetError(f"Saved NetCDF '{temp_path}' has no data variables.")
            except Exception as ex:
                raise InvalidDatasetError(f"Saved file is not a valid NetCDF dataset: {ex}") from ex

            # Atomic rename (POSIX atomic, Windows atomic replace)
            os.replace(temp_path, final_path)
            logger.info(f"Successfully cached dataset '{cache_key}' at '{final_path}'")
            return final_path

        except Exception as err:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            logger.error(f"Failed to atomically write cache file for '{cache_key}': {err}")
            raise err

    def clear(self, provider_subfolder: Optional[str] = None) -> None:
        """Clears cached files for a specific provider or entire cache."""
        target_dir = self.get_provider_cache_dir(provider_subfolder) if provider_subfolder else self.cache_root_dir
        if os.path.exists(target_dir):
            for filename in os.listdir(target_dir):
                file_path = os.path.join(target_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path) and not provider_subfolder:
                        shutil.rmtree(file_path)
                except Exception as e:
                    logger.warning(f"Error removing cached file {file_path}: {e}")
