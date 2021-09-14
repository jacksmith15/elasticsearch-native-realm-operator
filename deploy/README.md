# Local deployment configuration, for testing

Requires: `kind`, `ctlptl`, `kustomize`, `kubectl`

## Setup

Create the cluster:

```shell
ctlptl apply -f cluster.yaml
```

Set context to the newly created cluster:

```shell
kubectl config use-context kopf-test-cluster
```

Build and push the operator image to the local registry:

```shell
cd ..
poetry run inv push --version=latest --registry localhost:5005
cd -
```

Populate the cluster:

```shell
kustomize build base | kubectl apply -f -
```

You'll want to wait until all services are running, this could take some time.  Kibana will become available at [localhost:5005].

### Deploy the operator

```shell
kustomize build native-realm-operator | kubectl apply -f -
```

## Try out the operator

An example Elasticsearch user resource is available in [custom-user.yaml](base/elasticsearch/users/custom-user.yaml).  Test out creating this with:

```shell
kustomize build native-realm/elasticsearch/users | kubectl apply -f -
```

This will:
1. Create a secret called `elasticsearch-credentials-custom-user`
1. Create a corresponding user in Elasticsearch's native realm

Extract the generated password using:

```shell
kubectl get secret -n elasticsearch elasticsearch-custom-user-credentials -o json | jq -r '.data.password' | base64 -d
```

And use this to login on Kibana.

> :memo: The secret will be unchanged for further updates to the User.  Deleting the user will delete the secret.

## Teardown

Delete the cluster and registry:

```shell
ctlptl delete cluster --name kopf-test-cluster
ctlptl delete registry --name kopf-test-registry
```
