"""Unified logger configuration for Mem0 Dify Plugin.

This module provides a centralized logger configuration that ensures all logs
are properly output to the Dify plugin container using the official plugin logger handler.
"""

import logging

from dify_plugin.config.logger_format import plugin_logger_handler


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with Dify plugin handler configured.

    Args:
        name: Logger name (typically __name__ of the calling module)

    Returns:
        Configured logger instance

    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    # Only add handler if not already added to avoid duplicate logs
    if not logger.handlers:
        logger.addHandler(plugin_logger_handler)
    return logger

