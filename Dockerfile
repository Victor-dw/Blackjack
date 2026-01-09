FROM python:3.11-slim

WORKDIR /app

# NOTE: This is a skeleton. Add dependencies using your chosen package manager workflow.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt || true

COPY . /app

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "src.api.main"]
