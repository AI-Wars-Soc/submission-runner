from gevent import monkey
monkey.patch_all()

import main
from main import app

if __name__ == "__main__":
    main.run()
    app.run()
