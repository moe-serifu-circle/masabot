#!/usr/bin/env bash

if [[ ! -d .venv && ! -d venv ]]
then
    python -m virtualenv .venv
fi

./run-masabot.sh &
MASABOT_PID=$!
sleep 10

virtual_dir=

if [ -d .venv ]
then
    virtual_dir=.venv
elif [ -d venv ]
then
    virtual_dir=venv
fi

if [ -d "$virtual_dir/bin" ]
then
    virtual_dir="$virtual_dir/bin"
elif [ -d "$virtual_dir/Scripts" ]
then
    virtual_dir="$virtual_dir/Scripts"
else
    echo "Virtual environment not found in '$virtual_dir/bin' or '$virtual_dir/Scripts'." >&2
    echo "Please ensure setup is correct." >&2
    exit 1
fi

. "$virtual_dir/activate"

python -m unittest discover -s tests/integration -p "*_test.py"

kill -- -$$
