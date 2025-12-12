import logging


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

def log_interface(message, level="info"):

    if level == "info":
        logging.info(message)
    elif level == "warn":
        logging.warning(message)
    elif level == "error":
        logging.error(message)
    elif level == "success":
        logging.info(f"SUCCESS: {message}")
    else:
        logging.info(message)
