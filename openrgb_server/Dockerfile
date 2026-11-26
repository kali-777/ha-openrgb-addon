FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    QT_QPA_PLATFORM=offscreen \
    LANG=C.UTF-8

RUN echo "deb http://deb.debian.org/debian trixie main" > /etc/apt/sources.list.d/trixie.list \
    && printf "Package: *\nPin: release n=bookworm\nPin-Priority: 900\n\nPackage: openrgb*\nPin: release n=trixie\nPin-Priority: 990\n" > /etc/apt/preferences.d/openrgb \
    && apt-get update && apt-get install -y --no-install-recommends \
    openrgb \
    ddcutil \
    python3 \
    python3-paho-mqtt \
    jq \
    usbutils \
    i2c-tools \
    udev \
    libhidapi-hidraw0 \
    libhidapi-libusb0 \
    libusb-1.0-0 \
    ca-certificates \
    bash \
    && mkdir -p /etc/udev/rules.d \
    && if [ -f /usr/lib/udev/rules.d/60-openrgb.rules ]; then \
         mv /usr/lib/udev/rules.d/60-openrgb.rules /etc/udev/rules.d/60-openrgb.rules; \
       else \
         touch /etc/udev/rules.d/60-openrgb.rules; \
       fi \
    && rm -f /usr/lib/udev/rules.d/60-openrgb.rules /lib/udev/rules.d/60-openrgb.rules \
    && ldconfig \
    && rm -rf /var/lib/apt/lists/*

COPY ddc_service.py /ddc_service.py
COPY run.sh /run.sh
RUN chmod a+x /run.sh /ddc_service.py

WORKDIR /config

CMD [ "/run.sh" ]
