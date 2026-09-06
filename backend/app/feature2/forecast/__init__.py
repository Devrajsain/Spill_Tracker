"""
Forward slick movement forecasting pipeline.
"""

from .forecaster import ForwardForecaster, predict_slick_forecast, circular_mean_longitude

__all__ = [
    "ForwardForecaster",
    "predict_slick_forecast",
    "circular_mean_longitude",
]
