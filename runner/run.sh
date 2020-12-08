#!/bin/bash
rm -rv /sandbox-scripts/*
cp -rv /sandbox-scripts-src/* /sandbox-scripts/
python3 /runner/main.py