#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ -f "../venv/Scripts/activate" ]; then
    source "../venv/Scripts/activate"
fi

python manage.py runserver 127.0.0.1:8000
