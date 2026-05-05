FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir fastapi==0.115.12 uvicorn==0.34.2 docker==7.1.0

COPY app /app/app

EXPOSE 7070
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7070"]

