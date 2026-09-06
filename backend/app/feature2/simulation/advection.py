"""
Advection physics computation combining surface currents and wind leeway.
"""

import math
from typing import Tuple, Union
from ..config import WindageConfig
from ..schemas.simulation_schema import AdvectionVector
from ..data.base import CurrentSample, WindSample, VectorFieldSample


class AdvectionCalculator:
    """Computes Eulerian total velocity vectors at given particle spacetime locations."""

    def __init__(self, windage_config: WindageConfig):
        self.windage = windage_config

    def compute_velocity(
        self,
        current_sample: Union[CurrentSample, VectorFieldSample],
        wind_sample: Union[WindSample, VectorFieldSample],
    ) -> AdvectionVector:
        """
        Combines ocean current velocity (u_c, v_c) and 10m wind velocity (u_w, v_w) with leeway factor
        and Coriolis deflection angle:
        u_total = u_c + leeway * (u_w * cos(theta) - v_w * sin(theta))
        v_total = v_c + leeway * (u_w * sin(theta) + v_w * cos(theta))
        """
        leeway = self.windage.leeway_factor
        theta = math.radians(self.windage.deflection_angle_deg)

        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        u_wind_eff = leeway * (wind_sample.u * cos_t - wind_sample.v * sin_t)
        v_wind_eff = leeway * (wind_sample.u * sin_t + wind_sample.v * cos_t)

        u_total = current_sample.u + u_wind_eff
        v_total = current_sample.v + v_wind_eff

        return AdvectionVector(
            u_total_ms=u_total,
            v_total_ms=v_total,
            u_current_ms=current_sample.u,
            v_current_ms=current_sample.v,
            u_wind_ms=wind_sample.u,
            v_wind_ms=wind_sample.v
        )
