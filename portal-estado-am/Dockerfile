FROM mcr.microsoft.com/playwright/python:v1.57.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright chromium já vem instalado na imagem base
# mas garantir que o headless shell esteja disponível
RUN playwright install chromium --with-deps

COPY main.py .

CMD ["python", "main.py"]
