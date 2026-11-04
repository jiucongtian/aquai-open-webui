# Exact official 0.13.0 slim image already verified on the test server.
ARG BASE_IMAGE=open-webui-base:c38885a
FROM ${BASE_IMAGE}
ARG RELEASE_SHA
LABEL org.opencontainers.image.revision=${RELEASE_SHA}
LABEL org.opencontainers.image.title="小岁岁"
ENV WEBUI_NAME="小岁岁"
COPY backend/open_webui/env.py /app/backend/open_webui/env.py
COPY static/static/ /app/build/static/
COPY deploy/xiaosuisui/brand_image.py /tmp/brand_image.py
RUN python /tmp/brand_image.py && rm /tmp/brand_image.py
