ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.13-alpine3.21
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8

COPY rootfs /
RUN chmod +x /run.sh

CMD [ "/run.sh" ]
