#!/usr/bin/env sh

set -e

# Config must exist
if [ ! -f "/config/config.json" ]
then
  echo "[BOOTSTRAP] ERROR: Missing configuration file in /config/config.json" >&2
  echo "[BOOTSTRAP] ERROR: Start with -v host-dir:/config where host-dir is a path on host containing config.json" >&2
  exit 1
fi

# Config must contain discord-api-key
apikey="$(cat /config/config.json | jq -r '."discord-api-key"')"
if [ -z "$apikey" ]
then
  echo "[BOOTSTRAP] ERROR: Configuration file is missing Discord API key" >&2
  echo "[BOOTSTRAP] ERROR: Start with -v host-dir:/config where host-dir is a path on host containing config.json with valid value for 'discord-api-key'." >&2
  exit 2
fi

# Config must have at least one superop
if [ "$(cat /config/config.json | jq -r '.superops | length')" -lt 1 ]
then
  echo "[BOOTSTRAP] ERROR: Configuration file has no superops defined. At least one must be defined to function." >&2
  echo "[BOOTSTRAP] ERROR: Start with -v host-dir:/config where host-dir is a path on host containing config.json with at least one element in 'superops'." >&2
fi

# Warn if nothing mounted to /app/resources
if [ -f "/app/resources/.not-mounted" ]
then
  echo "[BOOTSTRAP] WARN: There is no volume mounted to /app/resources; RESOURCES WILL NOT BE PERSISTED." >&2
  echo "[BOOTSTRAP] WARN: Start with -v host-dir:/app/resources where host-dir is desired path on host to persist to fix this." >&2
fi

echo "[BOOTSTRAP] INFO: All checks complete, starting masabot..." >&2

supervisorctl start masabot
