ARG BASE
ARG UV
FROM ${UV} AS uv
FROM ${BASE} AS pythonbase
ARG PYTHON_APK
RUN apk add --no-cache "python-3.13=${PYTHON_APK}" libstdc++
FROM pythonbase AS install
COPY --from=uv /uv /bin/uv
COPY requirements.lock /build/requirements.lock
RUN python3.13 -m venv --without-pip /opt/venv && uv pip install --no-cache --python /opt/venv/bin/python --only-binary :all: --require-hashes -r /build/requirements.lock
COPY payload.zip /build/payload.zip
RUN python3.13 -m zipfile -e /build/payload.zip /app
ARG RUNTIME_UID
ARG RUNTIME_GID
FROM pythonbase
ARG REVISION
ARG RUNTIME_UID
ARG RUNTIME_GID
LABEL org.opencontainers.image.revision="${REVISION}"
ENV PATH="/opt/venv/bin:${PATH}" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MODEL_POLICY_HOME=/state/models
COPY --from=install /opt/venv /opt/venv
COPY --from=install /app /app
RUN mkdir /state && chown "${RUNTIME_UID}:${RUNTIME_GID}" /state && chmod 0700 /state
WORKDIR /app
USER ${RUNTIME_UID}:${RUNTIME_GID}
ENTRYPOINT ["python3.13", "-B", "-m", "console_app.server"]
CMD ["--help"]
