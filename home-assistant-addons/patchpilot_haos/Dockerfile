ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8

RUN apk add --no-cache python3

COPY rootfs /
RUN chmod +x /run.sh

CMD [ "/run.sh" ]
