FROM docker.m.daocloud.io/library/python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ARG PIP_INDEX_URL=""

WORKDIR /app

RUN sed -i 's@http://deb.debian.org@https://mirrors.aliyun.com@g; s@http://security.debian.org@https://mirrors.aliyun.com@g' /etc/apt/sources.list 2>/dev/null || true \
    && find /etc/apt/sources.list.d -type f -name '*.sources' -exec sed -i 's@http://deb.debian.org@https://mirrors.aliyun.com@g; s@http://security.debian.org@https://mirrors.aliyun.com@g' {} \; \
    && apt-get clean \
    && apt-get update -o Acquire::Check-Valid-Until=false \
    && apt-get install -y --no-install-recommends curl netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY build/current/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip wheel setuptools \
    && if [ -n "$PIP_INDEX_URL" ]; then pip install -i "$PIP_INDEX_URL" -r /tmp/requirements.txt; else pip install -r /tmp/requirements.txt; fi

COPY build/current/ /app
COPY docker/scripts/backend-entrypoint.sh /usr/local/bin/backend-entrypoint.sh
RUN chmod +x /usr/local/bin/backend-entrypoint.sh

ENTRYPOINT ["backend-entrypoint.sh"]
