FROM python:3.11-slim

WORKDIR /app
COPY apps/voice-agent/requirements.txt /tmp/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends \
	libglib2.0-0 \
	libstdc++6 \
	libgcc-s1 \
	ca-certificates \
	&& rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY apps/voice-agent/src /app/src
ENV PYTHONPATH=/app/src

CMD ["python", "/app/src/agent.py", "start"]

