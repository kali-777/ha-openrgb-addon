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
    ca-certificates \
    curl \
    kmod \
    libdrm2 \
    libglib2.0-0t64 \
    libgudev-1.0-0 \
    libusb-1.0-0 \
    libxrandr2 \
    && ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL -o /tmp/libddcutil.deb "http://deb.debian.org/debian/pool/main/d/ddcutil/libddcutil4_1.4.1-1_${ARCH}.deb" \
    && curl -fsSL -o /tmp/ddcutil.deb "http://deb.debian.org/debian/pool/main/d/ddcutil/ddcutil_1.4.1-1_${ARCH}.deb" \
    && (dpkg -i /tmp/libddcutil.deb /tmp/ddcutil.deb || apt-get install -y --fix-broken --no-install-recommends) \
    && rm -f /tmp/libddcutil.deb /tmp/ddcutil.deb \
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
