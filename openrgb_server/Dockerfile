FROM debian:sid-slim

ENV DEBIAN_FRONTEND=noninteractive \
    QT_QPA_PLATFORM=offscreen \
    LANG=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
    openrgb \
    python3 \
    python3-paho-mqtt \
    jq \
    usbutils \
    i2c-tools \
    udev \
    libhidapi-hidraw0 \
    libhidapi-libusb0 \
    libhidapi-dev \
    libusb-1.0-0 \
    libusb-1.0-0-dev \
    ca-certificates \
    curl \
    kmod \
    libdrm2 \
    libglib2.0-0t64 \
    libgudev-1.0-0 \
    libxrandr2 \
    iproute2 \
    iputils-ping \
    && ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL -o /tmp/libddcutil.deb "http://deb.debian.org/debian/pool/main/d/ddcutil/libddcutil4_1.4.1-1_${ARCH}.deb" \
    && curl -fsSL -o /tmp/ddcutil.deb "http://deb.debian.org/debian/pool/main/d/ddcutil/ddcutil_1.4.1-1_${ARCH}.deb" \
    && (dpkg -i /tmp/libddcutil.deb /tmp/ddcutil.deb || apt-get install -y --fix-broken --no-install-recommends) \
    && rm -f /tmp/libddcutil.deb /tmp/ddcutil.deb \
    && mkdir -p /etc/udev/rules.d \
    && (QT_QPA_PLATFORM=offscreen openrgb --generate-udev-rules /etc/udev/rules.d/60-openrgb.rules || true) \
    && rm -f /usr/lib/udev/rules.d/60-openrgb.rules /lib/udev/rules.d/60-openrgb.rules 2>/dev/null || true \
    && ldconfig \
    && rm -rf /var/lib/apt/lists/*

COPY ddc_service.py /ddc_service.py
COPY ghost_responder.py /ghost_responder.py
COPY run.sh /run.sh
RUN chmod a+x /run.sh /ddc_service.py /ghost_responder.py

WORKDIR /config

CMD [ "/run.sh" ]
