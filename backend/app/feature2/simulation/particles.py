from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from ..schemas.input_schema import SlickDetectionInput
from ..schemas.simulation_schema import Particle, ParticleEnsemble, ParticleState
from ..data.domain import SentinelObservationDomain
from ..geo.spatial import sample_particles_in_polygon


class ParticleManager:
    """Handles seeding, tracking, and spatial conversion of particle ensembles."""

    @staticmethod
    def seed_from_slick(
        slick: SlickDetectionInput,
        num_particles: int = 500,
        random_seed: Optional[int] = None
    ) -> ParticleEnsemble:
        """
        Seeds initial Lagrangian particles distributed across the observed SAR slick polygon.
        Maintains backward compatibility with ParticleEnsemble.
        """
        coords = slick.geometry.coordinates
        polygon_ring = coords[0] if slick.geometry.type == "Polygon" else coords[0][0]

        sampled_points = sample_particles_in_polygon(
            polygon_coords=polygon_ring,
            num_particles=num_particles,
            random_seed=random_seed
        )

        particles = [
            ParticleState(
                id=idx,
                latitude=lat,
                longitude=lon,
                timestamp=slick.observation_time,
                age_seconds=0.0,
                mass_kg=1.0,
                is_active=True,
                beached=False
            )
            for idx, (lat, lon) in enumerate(sampled_points)
        ]

        return ParticleEnsemble(
            spill_id=slick.spill_id,
            timestamp=slick.observation_time,
            particles=particles
        )

    @classmethod
    def seed_particles(
        cls,
        source: Union[SlickDetectionInput, SentinelObservationDomain, Dict[str, Any]],
        num_particles: int = 500,
        random_seed: Optional[int] = None
    ) -> List[Particle]:
        """
        Seeds a list of individual Particle objects directly from Feature 1 input or Sentinel domain.
        Guarantees deterministic unique IDs, valid internal coordinates, and observation timestamp.
        """
        if isinstance(source, dict):
            slick = SlickDetectionInput(**source)
            if slick.geometry.type == "MultiPolygon":
                raise NotImplementedError(
                    "MultiPolygon geometry seeding is not currently supported; input geometry must be 'Polygon'."
                )
            obs_time = slick.observation_time
            polygon_ring = slick.geometry.coordinates[0]
        elif isinstance(source, SlickDetectionInput):
            if source.geometry.type == "MultiPolygon":
                raise NotImplementedError(
                    "MultiPolygon geometry seeding is not currently supported; input geometry must be 'Polygon'."
                )
            obs_time = source.observation_time
            polygon_ring = source.geometry.coordinates[0]
        elif isinstance(source, SentinelObservationDomain):
            obs_time = source.observation_time
            # Construct polygon from bounding box if raw polygon not attached
            polygon_ring = [
                [source.min_lon, source.min_lat],
                [source.max_lon, source.min_lat],
                [source.max_lon, source.max_lat],
                [source.min_lon, source.max_lat],
                [source.min_lon, source.min_lat]
            ]
        else:
            raise ValueError(f"Unsupported particle seeding source type: {type(source)}")

        sampled_points = sample_particles_in_polygon(
            polygon_coords=polygon_ring,
            num_particles=num_particles,
            random_seed=random_seed
        )

        return [
            Particle(
                particle_id=f"p_{idx:04d}",
                latitude=lat,
                longitude=lon,
                timestamp=obs_time,
                active=True,
                age_seconds=0.0,
                mass_kg=1.0
            )
            for idx, (lat, lon) in enumerate(sampled_points)
        ]
