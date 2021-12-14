#!/usr/bin/env bash

# Time how long it takes to bring the cluster to ready state
start=$(date +%s%N)

docker-compose up -d

for i in $(seq 1 200);
do
    [ $i -gt 1 ] && sleep 2; kubectl --kubeconfig kubeconfig.yaml rollout status deployment/traefik -n kube-system && s=0 && break || s=$?
done

end=$(date +%s%N)
runtime=$((end-start))
runtime_seconds=$(echo "scale=2;${runtime}/1000000000" | bc)

echo "Started cluster in ${runtime_seconds}s"

unhealthy_pods=$(kubectl --kubeconfig kubeconfig.yaml get pods --all-namespaces -o json | jq '.items | map(select(.status.phase=="Running" | not)) | map(select(.status.phase=="Succeeded" | not)) | length')

echo "Number of unhealthy pods: ${unhealthy_pods}"

exit $s
