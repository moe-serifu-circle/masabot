#!/usr/bin/env python
# Evaluates stdin as a python data object and saves the contents as a state file.
import pickle
import sys

data = None
data_raw = sys.stdin.read()
try:
	data = eval(data_raw)
except Exception as e:
	print(str(e), file=sys.stderr)
	print("A problem occurred while reading the input.", file=sys.stderr)
	print("Ensure that the input is from a file created with the dumpstate.py script.", file=sys.stderr)
	exit(1)

if type(data) != dict:
	print("The data provided on stdin does not contain a python dict at the top level.", file=sys.stderr)
	print("Ensure that the input is from a file created with the dumpstate.py script.", file=sys.stderr)
	exit(2)

if '____CONTAINS_MASABOT_STATE_DATA____' not in data:
	print("The provided dict does not contain masabot state data created by the dumpstate.py script.", file=sys.stderr)
	print("Ensure that the input is from a file created with the dumpstate.py script.", file=sys.stderr)
	exit(3)

if not data['____CONTAINS_MASABOT_STATE_DATA____']:
	print("The provided dict has been explicitly marked as not having masabot state data.", file=sys.stderr)
	print("Ensure that the input is from a file created with the dumpstate.py script.", file=sys.stderr)
	exit(4)

del data['____CONTAINS_MASABOT_STATE_DATA____']

print("Saving to 'state2.p'; rename to state.p if changes are final")
with open("state2.p", "wb") as fp:
	pickle.dump(data, fp)
