FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --gid 10002 superviseur \
    && useradd --uid 10002 \
               --gid superviseur \
               --no-create-home \
               --no-log-init \
               --shell /usr/sbin/nologin \
               superviseur

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY superviseur.py .

USER 10002:10002

CMD ["python", "superviseur.py"]