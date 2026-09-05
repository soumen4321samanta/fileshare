#!/usr/bin/env bash
# Exit on error
set -o errexit
apt-get update && apt-get install -y tesseract-ocr

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# Auto-create an admin superuser on deploy, using env vars set in Render's
# dashboard (DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_EMAIL /
# DJANGO_SUPERUSER_PASSWORD). Safe to run on every deploy - it does nothing
# if that username already exists. This exists because Shell access isn't
# available on Render's free instance type.
python manage.py createsuperuser_if_none_exists || true
