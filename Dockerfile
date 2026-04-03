# Use official Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1

# Copy dependencies
COPY requirements.txt .

# Install system dependencies for psycopg and build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    postgresql-client \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Expose FastAPI port
EXPOSE 8008

# Run FastAPI with Uvicorn
CMD ["uvicorn", "main:app", "--host", "localhost", "--port", "8008"]

