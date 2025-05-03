# Dockerfile
FROM python:3.10-slim

WORKDIR /app

# Copy Python dependencies list first (for Docker cache)
COPY requirements.txt .

# Install all deps
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the source
COPY . .

# Expose port (Cloud Run listens on $PORT, default 8080)
ENV PORT 8080

# Use gunicorn to serve
CMD ["gunicorn", "-b", "0.0.0.0:8080", "app:app"]
