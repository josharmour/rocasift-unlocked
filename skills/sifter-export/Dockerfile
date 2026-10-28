FROM arm64v8/alpine:3.20
RUN apk add --no-cache python3 tar curl tzdata
COPY export-agent.py /usr/local/bin/export-agent.py
# Non-root user; the platform mounts privileged volumes at runtime.
RUN adduser -D -u 1000 exporter
USER exporter
# Config arrives via env vars set from the skill's inputs/module twin:
#   TARGET_PATHS, ENDPOINT_URL, INTERVAL_SECONDS, AUTH_TOKEN
ENTRYPOINT ["python3", "-u", "/usr/local/bin/export-agent.py"]
