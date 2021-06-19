#!/bin/bash
python -m gunicorn --workers=1 --worker-class=geventwebsocket.gunicorn.workers.GeventWebSocketWorker --worker-connections=1000 --bind 0.0.0.0:8080 wsgi:app
