"""Unified logger configuration for Mem0 Dify Plugin.

This module provides a centralized logger configuration that ensures all logs
are properly output to the Dify plugin container using the official plugin logger handler.
"""

import logging
import threading

from dify_plugin.config.logger_format import plugin_logger_handler

# Module-level log level cache (defaults to INFO)
_log_level = logging.INFO
_log_level_lock = threading.Lock()


def set_log_level(level: str) -> None:
    """Set global log level for all loggers.
    
    This function updates the log level for all existing loggers created by this module.
    It is thread-safe and can be called at runtime to dynamically adjust log verbosity.
    
    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR)
    
    """
    global _log_level
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    
    with _log_level_lock:
        _log_level = level_map.get(level.upper(), logging.INFO)
        # Update all existing loggers in tools and utils modules
        for logger_name in logging.Logger.manager.loggerDict:
            if logger_name.startswith("tools.") or logger_name.startswith("utils."):
                existing_logger = logging.getLogger(logger_name)
                existing_logger.setLevel(_log_level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with Dify plugin handler configured.

    Args:
        name: Logger name (typically __name__ of the calling module)

    Returns:
        Configured logger instance

    """
    logger = logging.getLogger(name)
    
    # Set to current global log level
    with _log_level_lock:
        logger.setLevel(_log_level)
    
    # Only add handler if not already added to avoid duplicate logs
    if not logger.handlers:
        logger.addHandler(plugin_logger_handler)
    
    return logger

