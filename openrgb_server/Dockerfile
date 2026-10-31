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
    && mkdir -p /etc/udev/rules.d /usr/lib/udev/rules.d /lib/udev/rules.d \
    && if [ -f /usr/lib/udev/rules.d/60-openrgb.rules ]; then \
         cp /usr/lib/udev/rules.d/60-openrgb.rules /etc/udev/rules.d/60-openrgb.rules; \
       else \
         touch /etc/udev/rules.d/60-openrgb.rules /usr/lib/udev/rules.d/60-openrgb.rules; \
       fi \
    && rm -rf /var/lib/apt/lists/*

COPY run.sh /run.sh
RUN chmod a+x /run.sh

WORKDIR /config

CMD [ "/run.sh" ]
