# Warehouse_web — Django BFF + QDE render host
# ADR-0032 D7 / TZ-QDE_INTEGRATION_READINESS §9.1: QDE installs as a Python
# package from the monorepo; Typst 0.15.1 is pinned and sha256-verified at
# build time; runtime download is forbidden.
#
# IMPORTANT: build context is the workspace ROOT (docker-compose sets
# `context: .`), so this file can COPY QuartermasterDocumentEngine/.
# Heavy/local artifacts are excluded via the root `.dockerignore`.

# ---------------------------------------------------------------------------
# Stage 1: builder — python deps + QDE package install
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

COPY Warehouse_web/requirements.txt ./
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r requirements.txt

# QDE from the monorepo (ADR-0031 D1): templates/fonts/contracts are delivered
# via [tool.setuptools.data-files] into share/quartermaster_document_engine/.
COPY QuartermasterDocumentEngine/ /build/QuartermasterDocumentEngine
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com /build/QuartermasterDocumentEngine

COPY Warehouse_web/ /build/Warehouse_web

# ---------------------------------------------------------------------------
# Stage 1.5: typst-fetch — build-time only (runtime download forbidden)
# fetch_typst.py resolves its pin as <script-parent>/spike/typst-pin.json
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS typst-fetch

WORKDIR /fetch

COPY QuartermasterDocumentEngine/scripts/fetch_typst.py /fetch/scripts/fetch_typst.py
COPY QuartermasterDocumentEngine/spike/typst-pin.json /fetch/spike/typst-pin.json

RUN python /fetch/scripts/fetch_typst.py --target-dir /usr/local/typst \
 && test -x /usr/local/typst/typst-0.15.1/typst-x86_64-unknown-linux-musl/typst

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# WeasyPrint native deps are kept: the legacy renderer is still needed
# (ADR-0030 D2; Phase 6D SHADOW requires it).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        fontconfig \
        fonts-dejavu-core \
        fonts-liberation \
        libffi8 \
        libgdk-pixbuf-2.0-0 \
        libharfbuzz-subset0 \
        libjpeg62-turbo \
        libopenjp2-7 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Typst 0.15.1 (pinned; sha256 verified in typst-fetch stage)
COPY --from=typst-fetch /usr/local/typst/typst-0.15.1/typst-x86_64-unknown-linux-musl/typst /usr/local/bin/typst
RUN chmod +x /usr/local/bin/typst && /usr/local/bin/typst --version

# QDE bundled fonts + templates (canonical runtime resources; ADR-0032 D7)
COPY QuartermasterDocumentEngine/fonts/ /opt/qde/fonts/
COPY QuartermasterDocumentEngine/templates/ /opt/qde/templates/

# Installed Python packages from the builder stage, incl. QDE and its
# share/ resources (templates/fonts/contracts via data-files).
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/share/quartermaster_document_engine /usr/local/share/quartermaster_document_engine

# Warehouse_web application code
COPY --from=builder /build/Warehouse_web /app

# QDE render environment (ADR-0032 D3/D7/D8, TZ §9.1/§9.2)
ENV QM_TYPST_BINARY=/usr/local/bin/typst
ENV QM_FONTS_DIR=/opt/qde/fonts
ENV QM_TEMPLATES_DIR=/opt/qde/templates
ENV TYPST_TIMESTAMP=1700000000
ENV DOCUMENTS_RENDER_MODE=legacy
ENV QDE_EMERGENCY_FALLBACK_ENABLED=false

EXPOSE 8001

CMD ["python", "manage.py", "runserver", "0.0.0.0:8001"]
