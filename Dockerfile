FROM python:3.9.4-slim

ENV LC_ALL="C.UTF-8"
ENV LANG="C.UTF-8"

ENV PYTHONUNBUFFERED="1"
ENV PYTHONFAULTHANDLER="1"
ENV PIP_NO_CACHE_DIR="false"
ENV PIP_DISABLE_PIP_VERSION_CHECK="on"
ENV PIP_DEFAULT_TIMEOUT="100"

ENV POETRY_VERSION=1.1.8

# System deps:
RUN pip install --upgrade pip
RUN pip install "poetry==$POETRY_VERSION"

# Copy only requirements to cache them in docker layer
WORKDIR /app
COPY poetry.lock pyproject.toml ./

# Project initialization:
RUN poetry config virtualenvs.create false \
  && poetry install --no-dev --no-interaction --no-ansi --no-root

# Copy folders, and files for a project:
COPY elasticsearch_native_realm_operator ./elasticsearch_native_realm_operator

# Set pythonpath so that the source files are discoverable
ENV PYTHONPATH="/app"

# Execute command
ENTRYPOINT kopf run --standalone elasticsearch_native_realm_operator/main.py
