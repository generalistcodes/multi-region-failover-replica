FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir fastapi==0.115.12 uvicorn==0.34.2 requests==2.32.3

COPY router.py /app/router.py

EXPOSE 8090
CMD ["uvicorn", "router:app", "--host", "0.0.0.0", "--port", "8090"]

