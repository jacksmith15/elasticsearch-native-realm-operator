#!/usr/bin/env bash
# Run this script to populate the images directory with saved docker images.  These will then be
# mounted onto the k3s server and agents, skipping image pull steps.
images=(
    rancher/klipper-helm:v0.6.4-build20210813
    rancher/library-traefik:2.4.8
    rancher/coredns-coredns:1.8.3
    rancher/local-path-provisioner:v0.0.19
    rancher/klipper-lb:v0.2.0
    rancher/metrics-server:v0.3.6
)

mkdir -p images

for image_tag in ${images[@]}
do
    docker pull $image_tag
    docker save $image_tag -o images/$(echo $image_tag | sed -e 's/[^A-Za-z0-9._-]/-/g').tar
done
