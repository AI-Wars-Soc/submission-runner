#!/bin/bash
docker pull aiwarssoc/sandbox
python -m gunicorn --workers=1 --threads=3 --worker-class=uvicorn.workers.UvicornWorker --worker-connections=1000 --bind 0.0.0.0:8080 --log-level debug main:app --timeout 90
