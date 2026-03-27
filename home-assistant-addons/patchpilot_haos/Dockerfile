ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base:latest
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8

RUN apk add --no-cache python3

COPY run.sh /run.sh
COPY rootfs /
RUN chmod +x /run.sh

CMD [ "/run.sh" ]
