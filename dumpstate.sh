#!/bin/bash

# Dumps the contents of the state file.

[ -f "state.p" ] || { echo "no state.p file found in the current directory" >&2 ; exit 1 ; }

python -c 'import pickle;import pprint;pprint.pprint(pickle.load(open("state.p", "rb")))'
