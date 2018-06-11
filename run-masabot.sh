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

rm -rf .supervisor-redeploy

while [ -n "$running" ]
do
    python masabot.py
    if [ -f '.supervisor-redeploy' ]
    then
        rm -rf .supervisor-redeploy
        git pull
    else
        running=
    fi
done
