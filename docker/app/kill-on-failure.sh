#!/usr/bin/env sh

# Wraps execution of other scripts, and if they fail, causes
# the entire container to shut down immediately.
#
# Pass script to execute and each of its arguments to this script
# to make script failure shutdown the container.

"$@"
status=$?

if [ "$status" -ne 0 ]
then
  echo "[KILL-ON-FAILURE] ERROR: command failed: $*" >&2
  echo "[KILL-ON-FAILURE] ERROR: deliberately killing container as pre-check failed" >&2
  kill -s SIGTERM 1
fi

exit "$status"
