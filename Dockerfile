# Use a lightweight Python base image
FROM python:3.9-slim

# Set a working directory for the application
WORKDIR /app

# Copy requirements first to leverage Docker’s layer caching
# If you keep a separate requirements.txt file:
#     redis
#     pymongo
#     python-dotenv
# plus any other libraries your script needs
COPY requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application code (including the .env file if needed)
COPY . /app

# Expose any port if your script needs one (likely not needed for a background worker)
# EXPOSE 8000

# By default, run the main script
CMD ["python", "mongo-redis-sync.py"]
