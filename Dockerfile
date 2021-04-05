FROM alpine:3.13.4

# masabot mountpoints -
# /config - provide a custom config.json in root of this volume
# /app/resources - REQUIRED FOR RESOURCE PERSISTENCE
# /logs - capture logging
# /state - state.p will be read from/saved in this directory

# supervisor is python based; installing it should handle py
# dep as well. but it will not auto-install pip, which we need
#
# build-base, python3-dev - needed for building py packages from source
# libffi-dev - needed specifically for building pynacl for voice support
# zlib-dev, jpeg-dev - Needed for Pillow build
# zlib, libjpeg - needed for Pillow use
RUN apk add supervisor=4.2.1-r0 py3-pip zlib jpeg jq build-base python3-dev libffi-dev zlib-dev jpeg-dev

# install masabot dependencies
COPY requirements.txt /
RUN pip install -r requirements.txt && rm requirements.txt && apk del libffi-dev zlib-dev jpeg-dev build-base python3-dev

# masa dirs for mountpoints && dir for supervisor
RUN mkdir /logs && \
    mkdir /state && \
    touch /state/.not-mounted && \
    mkdir /config && \
    mkdir /app && \
    mkdir /app/ipc && \
    mkdir /app/resources && \
    touch /app/resources/.not-mounted && \
    mkdir /var/log/supervisor

# copy in files
COPY docker/ /
COPY fonts /app/fonts
COPY masabot.py /app/masabot.py
COPY masabot /app/masabot

# permissions
RUN chmod +x /app/bootstrap.sh && chmod +x /app/kill-on-failure.sh

ENTRYPOINT ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisord.conf"]