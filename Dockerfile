# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
COPY . .

# Make ports 3001 and 3443 available to the world outside this container
EXPOSE 3001
EXPOSE 3443

# Define environment variable
ENV FLASK_APP FirmwareServer.py
ENV FLASK_RUN_HOST 0.0.0.0
ENV FLASK_RUN_PORT 3001

# Generate self-signed certificates if they don't exist (for HTTPS)
# Note: For production, you'd typically use proper certificates and a reverse proxy.
RUN if [ ! -f cert.pem ] || [ ! -f key.pem ]; then \
    openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365 \
    -subj "/C=XX/ST=State/L=City/O=Organization/OU=OrgUnit/CN=localhost"; \
    fi

# Run the application
# We will run the Flask development server directly.
# For production, consider using a more robust WSGI server like Gunicorn.
CMD ["python", "FirmwareServer.py"]