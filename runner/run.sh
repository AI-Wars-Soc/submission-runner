#!/bin/bash
gunicorn --workers=3 --worker-class=gevent --worker-connections=1000 --bind 0.0.0.0:8080 wsgi:app
