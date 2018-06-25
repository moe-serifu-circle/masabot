#!/bin/bash

# starts up masabot and redeploys when necessary

running=1

virtual_dir=

if [ -d .venv ]
then
    virtual_dir=.venv
elif [ -d venv ]
then
    virtual_dir=venv
else
    echo "Virtual environment not found in '.venv' or 'venv'." >&2
    echo "Please create one for masabot before executing." >&2
    exit 1
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

if [ -d ".supervisor" ]
then
    rm -rf ".supervisor/restart-command"
    rm -rf ".supervisor/status"
else
    mkdir ".supervisor"
fi

python supervisor/supervisor.py redeploy

while [ -n "$running" ]
do
    python masabot.py
    if [ -f ".supervisor/restart-command" ]
    then
        cmd="$(cat ".supervisor/restart-command")"
        rm -rf ".supervisor/restart-command"
        if [ "$cmd" = "redeploy" ]
        then
            git pull
            python supervisor/supervisor.py redeploy
        elif [ "$cmd" = "quit" ]
        then
            running=
            echo "Clean shutdown"
        fi
    else
        echo "Unclean shutdown; restarting bot in 30 seconds..."
        sleep 30
    fi
done
