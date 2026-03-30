FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn whitenoise

# Copy project files
COPY . .

# Collect static files into /app/staticfiles
RUN python manage.py collectstatic --noinput

# Single worker + threads for SQLite compatibility (SQLite doesn't support concurrent
# writes from multiple processes).  Upgrade to --workers N after migrating to PostgreSQL.
CMD ["gunicorn", "asi_track_manager.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "120"]
