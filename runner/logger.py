import logging

from cuwais.config import config_file

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s' if config_file.get("debug") else '%(message)s',
    level=logging.DEBUG if config_file.get("debug") else logging.WARNING,
    datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger("submission-runner")
