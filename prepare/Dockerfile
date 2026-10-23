ARG BUILD_FROM
FROM ${BUILD_FROM}

# openssl: the app signs its own certificate for https on 8998 (see app/tls.py).
RUN apk add --no-cache openssl

WORKDIR /opt/prepare
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app ./app
# Carried in the image so the app can install them into Home Assistant's
# config folder on start (app/installer.py).
COPY integration ./integration
COPY blueprints ./blueprints

# Data lives in /data (the app's data folder, included in HA backups) and
# options are read from /data/options.json. These are code defaults, because
# the base image's s6 init does not pass ENV through to CMD.
CMD ["python3", "-m", "app.main"]
