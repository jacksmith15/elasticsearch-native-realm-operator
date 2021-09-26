import subprocess

import pytest
from kopf.testing import KopfRunner

from elasticsearch_native_realm_operator import main
from elasticsearch_native_realm_operator.kopf_ext import CustomResource
from tests.utils import kubectl


_RESOURCE_DEFINITIONS = [
    model for model in vars(main).values() if isinstance(model, type) and issubclass(model, CustomResource)
]


@pytest.fixture(scope="session", autouse=True)
def _load_crds(wait_for_services):
    del wait_for_services
    kubectl.apply(*[resource.definition() for resource in _RESOURCE_DEFINITIONS])


@pytest.fixture(scope="session", autouse=True)
def namespace(_load_crds):
    namespace_ = "native-realm"
    subprocess.run(f"kubectl create namespace {namespace_}".split(" "))
    try:
        yield namespace_
    finally:
        subprocess.run(f"kubectl delete namespace {namespace_}".split(" "))


@pytest.fixture(scope="session", autouse=True)
def operator(namespace):
    with KopfRunner(f"run --namespace {namespace} --standalone elasticsearch_native_realm_operator/main.py".split(" "), timeout=10) as runner:
        yield runner


@pytest.fixture(scope="session", autouse=True)
def _cleanup_roles_and_users(operator, namespace):
    try:
        yield
    finally:
        subprocess.run(f"kubectl delete --all elasticsearchnativerealmusers --namespace {namespace}".split(" "))
        subprocess.run(f"kubectl delete --all elasticsearchnativerealmroles --namespace {namespace}".split(" "))
