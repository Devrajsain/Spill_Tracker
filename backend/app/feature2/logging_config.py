"""
Centralized logging configuration for Feature 2.
"""

import logging
import sys


def setup_logger(name: str = "feature2", level: str = "INFO") -> logging.Logger:
    """Configures and returns a structured logger for Feature 2 components."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | [%(name)s] %(filename)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        logger.propagate = False
    return logger


logger = setup_logger()
