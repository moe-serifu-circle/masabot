FROM alpine:3.13.4

# masabot mountpoints -
# /config - provide a custom config.json in root of this volume
# /app/resources - REQUIRED FOR RESOURCE PERSISTENCE
# /logs - capture logging

# supervisor is python based; installing it should handle py
# dep as well. but it will not auto-install pip, which we need
#
# build-base, python3-dev - needed for building py packages from source
# libffi-dev - needed specifically for building pynacl for voice support
# zlib-dev, jpeg-dev - Needed for Pillow build
# zlib, libjpeg - needed for Pillow use
RUN apk add supervisor=4.2.1-r0 py3-pip zlib jpeg build-base python3-dev libffi-dev zlib-dev jpeg-dev
RUN mkdir /var/log/supervisor

# install masabot dependencies
COPY requirements.txt /
RUN pip install -r requirements.txt && rm requirements.txt
RUN apk del libffi-dev python3-dev build-base py3-pip zlib-dev jpeg-dev && rm -rf ~/.cache/pip

# output for masabot logging file
RUN mkdir /logs

# masabot install locations (ipc is the new '.supervisor' since we are now using real supervisor and not the half-baked old impl.)
RUN mkdir /app && mkdir /app/ipc

# detect if user has mounted to resources so we can warn them if they didnt
RUN mkdir /app/resources && touch /app/resources/.not-mounted

# masabot config default location
RUN mkdir /config

# copy in files
COPY docker/ /
COPY fonts /app/fonts
COPY masabot.py /app/masabot.py
COPY masabot /app/masabot
COPY config-example.json /config/config.json

# permissions
RUN chmod +x /app/bootstrap.sh && chmod +x /app/kill-on-failure.sh

CMD ["/usr/bin/bash"]