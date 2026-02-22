FROM python:3.12-slim

WORKDIR /app

# For production: pin exact versions in requirements.txt and use a multi-stage build.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY api /app/api
COPY db_config.py /app/db_config.py

EXPOSE 8001

# For production: run behind a reverse proxy and consider multiple workers.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
