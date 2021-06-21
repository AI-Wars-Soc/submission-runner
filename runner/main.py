from eventlet import monkey_patch

monkey_patch()

import cuwais.database
import eventlet.wsgi

from runner.logger import logger
from runner.app import app


if __name__ == "__main__":
    logger.debug("STARTING")
    cuwais.database.create_tables()
    # app.run(host="0.0.0.0", port=8080)
    eventlet.wsgi.server(eventlet.listen(('0.0.0.0', 8080)), app)
