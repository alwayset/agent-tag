# Agent Tag — open AI teammate for group chat.
# Slim image that installs the package with the web admin console plus all
# chat-platform adapters and LLM backends, and serves on :8765.
FROM python:3.12-slim

# Don't write .pyc, unbuffered stdout/stderr (so logs stream), no pip cache.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # SQLite lives on the /data volume so it survives container restarts.
    AGENT_TAG_DB=/data/agent_tag.db

WORKDIR /app

# Copy the project and install with the web + all chat/LLM extras.
COPY . .
RUN pip install '.[all]'

# Persisted SQLite database (admin settings, memory, audit, usage).
RUN mkdir -p /data

# Run as a non-root user; give it ownership of the app + data dirs.
RUN useradd --create-home --uid 10001 agent \
    && chown -R agent:agent /app /data
USER agent

VOLUME ["/data"]
EXPOSE 8765

# Default: the production runtime (admin console + chat adapters + ambient).
# Bind to 0.0.0.0 so the console is reachable from outside the container.
CMD ["agent-tag", "serve", "--host", "0.0.0.0"]
