import logging.config
import os


# log_level = os.getenv("LOG_LEVEL", "INFO").upper()


def setup_logging(
    app_name: str,
    log_level: str = "DEBUG",
    log_dir: str = "logs",
) -> None:
    """
    Setup logging configuration with both file and console handlers

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory to store log files
        app_name: Application name for log file naming
    """
    # Create logs directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "simple": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "simple",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": log_level,
                "formatter": "simple",
                "filename": os.path.join(log_dir, f"{app_name}.log"),
                "maxBytes": 10485760,  # 10MB
                "backupCount": 1,
            },
        },
        "loggers": {
            "": {"handlers": ["console", "file"], "level": "INFO"},
            "agentic_ai": {
                "handlers": ["console", "file"],
                "level": log_level,
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(config)
