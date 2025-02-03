import logging


def get_logger(logger_name: str, log_level: int = logging.DEBUG) -> logging.Logger:
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)
    logger.propagate = False  # Prevent log propagation to avoid double logging

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(console_handler)

    return logger
