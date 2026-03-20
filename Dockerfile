FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends docker.io && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir fastapi uvicorn psycopg2-binary python-dotenv
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]
