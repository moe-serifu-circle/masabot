#!/bin/bash

if [ "$#" -lt 1 ]
then
  echo "give tag to run as argument (e.g. \"1.6.0\")"
  exit 1
fi

if [ ! -f config.json ]
then
  echo "create config.json before running this command"
  exit 1
fi

[ -d "config" ] || mkdir config
[ -d "logs" ] || mkdir logs
cp config.json config/config.json

docker run \
  -v config:/config \
  -v resources:/app/resources \
  -v logs:/logs
  "masabot:$1" masabot