ARG PYTHON_VERSION=3.14.4
FROM python:${PYTHON_VERSION}-slim

ARG CONSTRAINTS=requirements/constraints-ha-2026.10.txt
WORKDIR /workspace
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libffi-dev libssl-dev nodejs \
    && rm -rf /var/lib/apt/lists/*
COPY requirements_dev.txt ./
COPY requirements/ ./requirements/
RUN python -m pip install --no-cache-dir -r requirements_dev.txt -c "${CONSTRAINTS}" \
    && python -m pip check
COPY custom_components/ ./custom_components/
COPY tests/ ./tests/
COPY pytest.ini ruff.toml ./
CMD ["sh", "-c", "python -m pytest -q && node --test tests/js/*.test.js && python -m ruff check ."]
