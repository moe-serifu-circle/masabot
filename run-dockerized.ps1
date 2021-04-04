#!/usr/bin/env powershell

# run this one from git bash on windows

param ([Parameter(Position=0,mandatory=$true)] [string] $tag)

Write-Host "This is a quick and dirty script to run on win, use after creating log, resources, and config dir and making a config.json"

$letter = (Split-Path -Path $pwd -Qualifier).Replace(":", "").ToLower()
$wd = (Split-Path -Path $pwd -NoQualifier)
$wd = $wd.Replace("\", "/")
$wd = "/" + $letter + $wd

Copy-Item -Path .\config.json -Destination .\config\config.json

docker build . -t "masabot:$tag"
docker rm -f masabot
docker run -v ${wd}/config:/config -v ${wd}/resources:/app/resources -v ${wd}/logs:/logs --name masabot masabot:$tag