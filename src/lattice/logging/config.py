"""Logging configuration for Lattice.

This module provides logging setup using Python's standard logging module
with external INI configuration file support.
"""

from __future__ import annotations

import logging
import logging.config
import os
from pathlib import Path

# Track whether logging has been configured
_configured = False


def configure_logging(config_path: str | Path | None = None, force: bool = False) -> None:
    """
    Configure logging for Lattice using an INI configuration file.

    Parameters
    ----------
    config_path : str, Path, or None
        Path to logging configuration file. If None, checks the
        LATTICE_LOGGING_CONFIG environment variable, then falls back
        to the default bundled configuration.
    force : bool
        If True, reconfigure logging even if already configured.
        Defaults to False.

    Notes
    -----
    The configuration file should follow Python's logging.config.fileConfig
    format (INI style).
    """
    global _configured

    if _configured and not force:
        return

    # Determine config path
    if config_path is None:
        env_path = os.environ.get("LATTICE_LOGGING_CONFIG")
        config_path = Path(env_path) if env_path else Path(__file__).parent / "logging.conf"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        # Fall back to basic configuration if config file not found
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
        )
        logging.getLogger("lattice").warning(
            "Logging config not found at %s, using basic configuration",
            config_path,
        )
    else:
        logging.config.fileConfig(
            config_path,
            disable_existing_loggers=False,
        )

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    This is a convenience wrapper around logging.getLogger that ensures
    consistent logger naming within the Lattice namespace.

    Parameters
    ----------
    name : str
        The logger name. Typically __name__ from the calling module.

    Returns
    -------
    logging.Logger
        A logger instance.
    """
    return logging.getLogger(name)
