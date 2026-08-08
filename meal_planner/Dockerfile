FROM python:3.12-slim

# The meal planner uses only the Python standard library, so there is nothing
# to pip install. That is why this image is small and builds quickly on a Pi.

# tzdata is the one exception, and it matters: this image is not one of the
# official Home Assistant base images, so it has no timezone database and would
# run in UTC. Supervisor passes a TZ environment variable in, but Python can
# only act on it if the zone files are present. Without this the planner rolls
# over to "tomorrow" an hour early during BST.
# openssl is the second exception. The app signs its own certificate so phones
# can reach it over https - which is what browsers require before they will
# cache anything for offline use. Only the command-line tool is missing from
# this image; Python's ssl module is already here.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata openssl \
    && rm -rf /var/lib/apt/lists/*

ENV MEAL_PLANNER_DATA_DIR=/data \
    MEAL_PLANNER_PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Every module, by glob rather than by name. This was an explicit list, which
# meant a new module was one forgotten word away from an add-on that refuses to
# start - and it fails only in the built image, because dev_mode runs from the
# folder where the file is present either way. That is the worst shape a bug can
# have here: it takes the kitchen display down, and only on a release.
COPY *.py ./
COPY static/ ./static/

# The app's own manifest, carried into the image for one reason: backup.py reads
# the version out of it and stamps it into every backup, so a zip found in a
# downloads folder in two years can say what made it. In dev_mode the file is
# beside the source anyway; without this line the built image is the only place
# the version comes out as "unknown".
COPY config.yaml ./

# First-run seed data. Copied into /data by run.sh only if /data is empty, so
# it never overwrites the live meal plan on an update.
COPY seed/ ./seed/

COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 8080

CMD ["/run.sh"]
