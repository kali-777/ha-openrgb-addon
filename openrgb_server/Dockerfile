ARG BUILD_FROM=debian:bookworm-slim
FROM ${BUILD_FROM}

ENV DEBIAN_FRONTEND=noninteractive \
    QT_QPA_PLATFORM=offscreen \
    LANG=C.UTF-8

ARG BUILD_ARCH=amd64

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
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
    libmbedtls14 \
    libqt5core5a \
    libqt5gui5 \
    libqt5widgets5 \
    && case "${BUILD_ARCH}" in \
         "aarch64"|"arm64") OPENRGB_ARCH="arm64" ;; \
         "armv7"|"armhf"|"arm") OPENRGB_ARCH="armhf" ;; \
         *) OPENRGB_ARCH="amd64" ;; \
       esac \
    && echo "Downloading OpenRGB 1.1 for ${OPENRGB_ARCH} on Debian Bookworm..." \
    && curl -fsSL -o /tmp/openrgb.deb "https://github.com/CalcProgrammer1/OpenRGB/releases/download/release_1.1/openrgb_1.1_${OPENRGB_ARCH}_bookworm_8e16de2.deb" \
    && (dpkg -i /tmp/openrgb.deb || apt-get install -y --fix-broken --no-install-recommends) \
    && rm -f /tmp/openrgb.deb \
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
