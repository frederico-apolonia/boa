#! /bin/bash

tag=$(date +'%Y%m%d%H%M')

docker build \
    --build-arg USERNAME=$(id -un) \
    --build-arg USERID=$(id -u) \
    --build-arg GROUPID=$(id -g) \
    --file ble/docker/Dockerfile \
    --no-cache \
    --tag ble:$tag \
    .

docker tag ble:$tag ble:latest

echo ble:$tag
echo ble:latest