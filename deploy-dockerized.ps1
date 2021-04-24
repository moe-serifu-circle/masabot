#!/usr/bin/env powershell

# run this one from git bash on windows

param ([Parameter(Position=0,mandatory=$true)] [string] $tag)

$hostname = "megumin.moeserifu"
$tld = "moe"
$port = "8047"
$hostUrl = $hostname + "." + $tld + ":" + $port
$remoteImg = $hostUrl + "/moeserifu/masabot"
$remoteVer = $remoteImg + ":" + $tag
$remoteLat = $remoteImg + ":latest"

docker tag masabot:$tag $remoteVer
docker tag masabot:$tag $remoteLat
docker push $remoteVer
docker push $remoteLat
