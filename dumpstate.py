#!/usr/bin/env python
# Dumps the contents of the state file.
import pickle
import pprint
import sys

try:
	with open('state.p', 'rb') as fp:
		data = pickle.load(fp)
except FileNotFoundError:
	print("no state.p file found in the current directory", file=sys.stderr)
else:
	data['____CONTAINS_MASABOT_STATE_DATA____'] = True
	pprint.pprint(data)

