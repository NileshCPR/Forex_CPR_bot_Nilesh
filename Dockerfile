FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p /app/data /app/logs && \
    chmod -R 755 /app && \
    chmod 666 /app/data/users.json 2>/dev/null || true

# Expose port for web service
EXPOSE 10000

# Run the application
CMD ["python", "main.py"]