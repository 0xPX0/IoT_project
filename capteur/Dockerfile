FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --gid 10001 iot \
    && useradd --uid 10001 \
               --gid iot \
               --no-create-home \
               --no-log-init \
               --shell /usr/sbin/nologin \
               iot

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY capteur.py .

USER 10001:10001

CMD ["python", "capteur.py"]