# Start with an official Python image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY . .

# Expose the port the app runs on (default 8000, override via $PORT)
EXPOSE 8000

# Shell form so $PORT is expanded at runtime (Railway sets $PORT; defaults to 8000 elsewhere)
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
