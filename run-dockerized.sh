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
#cat config.json
#cp config.json config/config.json

docker build . -t "masabot:$1"
docker stop masabot
docker rm masabot
docker run \
  -v "$(pwd)/config":/config \
  -v "$(pwd)/resources":/app/resources \
  -v "$(pwd)/logs:/logs" \
  --name masabot \
  "masabot:$1"
