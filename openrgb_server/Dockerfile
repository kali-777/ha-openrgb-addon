ARG BUILD_FROM=debian:sid-slim
FROM ${BUILD_FROM}

ENV DEBIAN_FRONTEND=noninteractive \
    QT_QPA_PLATFORM=offscreen \
    LANG=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    openrgb \
    jq \
    usbutils \
    i2c-tools \
    udev \
    libhidapi-hidraw0 \
    libhidapi-libusb0 \
    libusb-1.0-0 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY run.sh /run.sh
RUN chmod a+x /run.sh

WORKDIR /config

CMD [ "/run.sh" ]
