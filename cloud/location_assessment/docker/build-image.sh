# !/bin/bash
tag=$(date +'%Y%m%d%H%M')

docker build \
    --build-arg USERNAME=$(id -un) \
    --build-arg USERID=$(id -u) \
    --build-arg GROUPID=$(id -g) \
    --file location_assessment/docker/Dockerfile \
    --no-cache \
    --tag sato-boa-location-assessment-service:$tag \
    .

docker tag sato-boa-location-assessment-service:$tag sato-boa-location-assessment-service:latest

echo sato-boa-location-assessment-service:$tag
echo sato-boa-location-assessment-service:latest