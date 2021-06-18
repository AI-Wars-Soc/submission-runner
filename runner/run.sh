#!/bin/bash
gunicorn --bind 0.0.0.0:8080 runner/wsgi:app
