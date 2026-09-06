"""
Custom domain exceptions for Feature 2.
"""


class Feature2Error(Exception):
    """Base exception for all Feature 2 errors."""
    pass


class InvalidInputGeometryError(Feature2Error):
    """Raised when SAR slick geometry is malformed, self-intersecting, or out of geographical bounds."""
    pass


class EnvironmentalDataError(Feature2Error):
    """Base class for environmental data layer errors."""
    pass


class EnvironmentalDataUnavailableError(EnvironmentalDataError):
    """Raised when oceanographic or meteorological data cannot be fetched or opened."""
    pass


class InvalidDatasetError(EnvironmentalDataError):
    """Raised when an environmental dataset (e.g. NetCDF) fails validation (missing variables, wrong dimensions, invalid coordinates)."""
    pass


class EnvironmentalCoverageError(EnvironmentalDataError):
    """Raised when an environmental dataset does not fully cover the spatial or temporal domain required by a Sentinel-1 observation."""
    pass


class OutOfDomainError(EnvironmentalCoverageError):
    """Raised when requested coordinates lie outside the spatial domain of the environmental dataset."""
    pass


class TemporalCoverageError(EnvironmentalCoverageError):
    """Raised when requested timestamp lies outside the available temporal coverage of the dataset."""
    pass


class SimulationError(Feature2Error):
    """Raised when the particle advection simulation encounters numerical instability or out-of-domain particles."""
    pass


class OriginConvergenceError(Feature2Error):
    """Raised when backward reconstruction fails to converge on identifiable candidate origin clusters."""
    pass


class ConfigurationError(Feature2Error):
    """Raised when configuration parameters are contradictory or invalid."""
    pass
