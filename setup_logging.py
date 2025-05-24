import logging
from pathlib import Path
import logging.config
from config import BaseConfig 
from datetime import datetime

def get_logger(name: str, log_dir: Path, level: str = "INFO", session_id: str = None, case_name: str = None) -> logging.Logger:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"logs_{timestamp}_{case_name}_{session_id}.log"

    log_dir.mkdir(parents=True, exist_ok=True)

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": level,
            },
            "file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "formatter": "standard",
                "when": "midnight",
                "backupCount": 14,
                "filename": str(log_dir/log_filename),
                "encoding": "utf-8",
                "level": "DEBUG",
            },
        },
        "root": {
            "handlers": ["console", "file"],
            "level": level,
        },
    })

    return logging.getLogger(name)
