# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Use --no-cache-dir to reduce image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
# This includes app.py and your tool files (flight.py, hotels.py, etc.)
COPY . .

# Make port 8501 available to the world outside this container (Streamlit's default port)
EXPOSE 8501

# Define environment variable for Streamlit's health check (optional but good practice)
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

# Run app.py when the container launches using streamlit run
# Use --server.address=0.0.0.0 to make it accessible outside the container
# Use --server.port=8501 to specify the port
ENTRYPOINT ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
