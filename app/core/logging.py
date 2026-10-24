"""Logging configuration with JSON formatting."""

import logging
import logging.config
import sys
from pathlib import Path

from pythonjsonlogger import jsonlogger

from app.core.config import settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields."""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["app"] = settings.APP_NAME
        log_record["env"] = settings.APP_ENV
        log_record["level"] = record.levelname
        log_record["logger"] = record.name


def setup_logging() -> None:
    """Configure application logging."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Ensure log directory exists
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": CustomJsonFormatter,
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
            },
            "console": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "console",
                "stream": sys.stdout,
                "level": log_level,
            },
            "file_json": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "json",
                "filename": log_dir / "app.json.log",
                "maxBytes": 10_485_760,  # 10MB
                "backupCount": 5,
                "level": log_level,
            },
            "file_error": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "json",
                "filename": log_dir / "error.json.log",
                "maxBytes": 10_485_760,
                "backupCount": 5,
                "level": logging.ERROR,
            },
        },
        "loggers": {
            "": {  # Root logger
                "handlers": ["console", "file_json", "file_error"],
                "level": log_level,
                "propagate": True,
            },
            "uvicorn": {
                "handlers": ["console", "file_json"],
                "level": "INFO",
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "handlers": ["console", "file_json"],
                "level": "WARNING",
                "propagate": False,
            },
            "alembic": {
                "handlers": ["console", "file_json"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(config)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)