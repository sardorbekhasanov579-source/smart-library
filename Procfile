web: gunicorn library_project.wsgi:application --workers 2 --timeout 120
release: python manage.py migrate --no-input
