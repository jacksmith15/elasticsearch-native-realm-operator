from invoke import Collection, task
from tasks.helpers import package, print_header


local = Collection("local")


@task()
def build(ctx, version="latest"):
    """Build docker image."""
    print_header("Building image")
    ctx.run(f"docker build . --tag elasticsearch-native-realm-operator:{package.__version__}")


@task(pre=[build])
def push(ctx, registry="localhost:5005", version="latest", reload=True, context="kind-kopf-test-cluster"):
    """Push docker image to local registry, and reload deployment."""
    if version == "package":
        version = package.__version__
    tag = f"{registry}/elasticsearch-native-realm-operator:{version}"
    print_header(f"Tagging and pushing image: {tag!r}")
    ctx.run(f"docker build . --tag {tag}")
    ctx.run(f"docker push {tag}")
    if not reload:
        return
    print_header("Reloading deployment")
    ctx.run(
        f"kubectl --context {context} rollout restart -n elastic-system deployments/native-realm-operator"
    )
    ctx.run(
        f"kubectl --context {context} rollout status -n elastic-system deployments/native-realm-operator"
    )


local.add_task(build)
local.add_task(push)
