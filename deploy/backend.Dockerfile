# Backend FastAPI invoice web.
# Kode & data TIDAK di-copy ke image -- di-bind-mount saat runtime, mengikuti
# pola CARA-DEPLOY.md (deploy = git merge, bukan rebuild image). Image ini
# hanya berisi Python + dependency.
FROM python:3.12-slim

# Font TTF utk reportlab (PDF invoice) -- python:slim tidak bawa font sama sekali.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core poppler-utils \
 && rm -rf /var/lib/apt/lists/*

# Hanya webapp/requirements.txt yang masuk build context (lihat .dockerignore).
COPY webapp/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    "reportlab>=4.0,<5.0" "openpyxl>=3.1,<4.0"

# Runtime: kode di /app (bind mount), data runtime di /data (INVOICE_DATA).
WORKDIR /app/webapp
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
