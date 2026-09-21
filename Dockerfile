# Stage 1: Build dependencies
FROM python:3.11-alpine AS builder

WORKDIR /build

# Install build dependencies for MySQL, cryptography, Pillow
RUN apk add --no-cache \
    gcc \
    musl-dev \
    mysql-dev \
    libffi-dev \
    openssl-dev \
    zlib-dev \
    jpeg-dev

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-alpine

WORKDIR /app

# Install runtime dependencies only
RUN apk add --no-cache \
    mysql-client \
    libffi \
    openssl \
    zlib \
    jpeg \
    postgresql-client

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Set PATH for pip installs
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=SparkService.settings

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p logs media staticfiles && \
    chmod +x manage.py

# Expose port
EXPOSE 8000

# Default command: Daphne (ASGI server for Django + Channels)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "SparkService.asgi:application"]
