# Simplified build for executor service using precompiled TA-Lib wheel
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies including precompiled TA-Lib wheel as root
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user and set ownership
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app

# Copy application code
COPY . .

# Copy uvicorn log configuration
COPY src/executor/uvicorn_log.conf /etc/uvicorn_log.conf

# Change ownership to appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Make sure scripts in .local are usable
ENV PATH=/home/appuser/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Expose port
EXPOSE 8002

# Run the application with uvicorn
CMD ["python", "-m", "src.executor.main"]
