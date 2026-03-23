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

# 3 workers is plenty for 15 concurrent users; timeout=120 handles slow queries gracefully
CMD ["gunicorn", "asi_track_manager.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
