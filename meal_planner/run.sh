#!/bin/sh
# Home Meal Planner - add-on entrypoint.
#
# /data is the add-on's persistent volume. It survives add-on updates,
# restarts and Home Assistant upgrades, and it is included in Home Assistant
# backups. Everything the app writes goes there.
set -e

if [ ! -f /data/data.json ] && [ -f /app/seed/data.json ]; then
  echo "[meal-planner] First run: seeding /data/data.json from the bundled copy."
  cp /app/seed/data.json /data/data.json
fi

if [ ! -d /data/images ] && [ -d /app/seed/images ]; then
  echo "[meal-planner] First run: seeding meal photos into /data/images."
  cp -r /app/seed/images /data/images
fi

mkdir -p /data/images

# Note: the rolling daily backup of data.json used to live here, but running it
# only at container start meant a long-lived add-on made no backups in between.
# server.py now does it on a timer, so it happens every day the app is running.

# ---------------------------------------------------------------- dev mode
#
# With dev_mode on, run the source straight from the add-ons folder instead of
# the copy baked into the image, so edits need only a Restart, not a Rebuild.
#
# server.py works out BASE_DIR from __file__, so static/ is picked up from the
# same live folder automatically, and the modules beside it resolve there too
# because Python puts the script's own directory first on sys.path.
#
# MEAL_PLANNER_DATA_DIR still points at /data either way, so the meal plan and
# photos are the same in both modes.
#
# There is no bashio in this image (it is not an HA base image), so the option
# is read from /data/options.json with the Python that is already here.

APP=/app/server.py
DEV_APP=/addons/meal_planner/server.py

DEV_MODE=0
if [ -f /data/options.json ]; then
  DEV_MODE=$(python3 -c "import json
try:
    print(1 if json.load(open('/data/options.json')).get('dev_mode') else 0)
except Exception:
    print(0)" 2>/dev/null || echo 0)
fi

# ------------------------------------------------------------------- https
#
# Off by default. On, the app also listens on 8443 with a certificate it signs
# itself, stored in /data/certs so it survives updates. This exists because
# browsers only allow offline caching (a service worker) on an https origin.
# Plain http on 8080 is untouched either way - the Nest Hub needs it.

if [ -f /data/options.json ]; then
  HTTPS_ON=$(python3 -c "import json
try:
    print(1 if json.load(open('/data/options.json')).get('https_enabled') else 0)
except Exception:
    print(0)" 2>/dev/null || echo 0)
  CERT_HOSTS=$(python3 -c "import json
try:
    print((json.load(open('/data/options.json')).get('cert_hosts') or '').strip())
except Exception:
    print('')" 2>/dev/null || echo "")
  if [ "$HTTPS_ON" = "1" ]; then
    export MEAL_PLANNER_HTTPS_PORT=8443
    [ -n "$CERT_HOSTS" ] && export MEAL_PLANNER_CERT_HOSTS="$CERT_HOSTS"
    echo "[meal-planner] HTTPS enabled on 8443. Set phones up at http://<pi>:8080/setup"
  fi
fi

# --------------------------------------------------------- kitchen display
#
# Which Cast device the kitchen display goes to. Empty - the normal case - means
# the app owns the choice and stores it in /data/cast.json; a value here pins it
# and the app's picker goes read-only, so there is never a question of which of
# the two won. cast_url is an escape hatch for a network where the address the
# add-on works out for itself is wrong.

if [ -f /data/options.json ]; then
  CAST_DEVICE=$(python3 -c "import json
try:
    print((json.load(open('/data/options.json')).get('cast_device') or '').strip())
except Exception:
    print('')" 2>/dev/null || echo "")
  CAST_URL=$(python3 -c "import json
try:
    print((json.load(open('/data/options.json')).get('cast_url') or '').strip())
except Exception:
    print('')" 2>/dev/null || echo "")
  [ -n "$CAST_DEVICE" ] && export MEAL_PLANNER_CAST_DEVICE="$CAST_DEVICE"
  [ -n "$CAST_URL" ] && export MEAL_PLANNER_CAST_URL="$CAST_URL"
  [ -n "$CAST_DEVICE" ] && echo "[meal-planner] Kitchen display pinned to $CAST_DEVICE"
fi

if [ "$DEV_MODE" = "1" ]; then
  if [ -f "$DEV_APP" ]; then
    APP="$DEV_APP"
    echo "[meal-planner] DEV MODE: running live source from $(dirname "$DEV_APP")."
    echo "[meal-planner] Edit the files, then Restart. Rebuild is only needed for a release."
  else
    # Most likely the share is offline or the folder was renamed. Falling back
    # beats refusing to start and taking the kitchen display down with it.
    echo "[meal-planner] dev_mode is on, but $DEV_APP was not found."
    echo "[meal-planner] Falling back to the copy baked into the image."
  fi
fi

echo "[meal-planner] Starting on port ${MEAL_PLANNER_PORT}."
exec python3 "$APP"
