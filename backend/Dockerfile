FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# backend/ 直下の全 .py ファイルをコピー（tests/ や .venv/ は除外）
COPY *.py ./

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
