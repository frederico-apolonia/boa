# !/bin/bash
tag=$(date +'%Y%m%d%H%M')

docker build \
    --build-arg USERNAME=$(id -un) \
    --build-arg USERID=$(id -u) \
    --build-arg GROUPID=$(id -g) \
    --file salt-service/docker/Dockerfile \
    --no-cache \
    --tag sato-boa-salt-service:$tag \
    .

docker tag sato-boa-salt-service:$tag sato-boa-salt-service:latest

echo sato-boa-salt-service:$tag
echo sato-boa-salt-service:latest