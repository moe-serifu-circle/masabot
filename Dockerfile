FROM alpine:3.13.4

# masabot mountpoints -
# /app/config - provide a custom config.json in root of this volume
# /app/resource - REQUIRED FOR RESOURCE PERSISTENCE
# /app/logs - capture logging

# supervisor is python based; installing it should handle py
# dep as well
RUN apk add supervisor=4.2.1-r0
RUN mkdir /var/log/supervisor

# install masabot dependencies
COPY requirements.txt /
RUN pip install -r requirements.txt && rm -rf requirements.txt

# output for masabot logging file
RUN mkdir /logs

# masabot install locations (ipc is the new '.supervisor' since we are now using real supervisor and not the half-baked old impl.)
RUN mkdir /app && mkdir && mkdir /app/ipc

# detect if user has mounted to resources so we can warn them if they didnt
RUN mkdir /app/resources && touch /app/resources/.not-mounted

# masabot config default location
RUN mkdir /config

# copy in files
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf
COPY fonts /app/fonts
COPY masabot.py /app/masabot.py
COPY masabot /app/masabot
COPY config-example.json /config/config.json
CMD ["/usr/bin/supervisord"]