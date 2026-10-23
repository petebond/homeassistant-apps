#!/bin/sh
# Run the app locally for development: data in prepare/.devdata, plain http on 8999.
cd "$(dirname "$0")/.." || exit 1
mkdir -p .devdata
PREPARE_DATA=.devdata PREPARE_OPTIONS=/nonexistent exec python3 -m app.main
