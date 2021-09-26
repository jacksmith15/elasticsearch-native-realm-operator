import os
import subprocess
from pathlib import Path

import elasticsearch
import pytest
import yaml
from pytest_docker.plugin import Services

from elasticsearch_native_realm_operator.client import elasticsearch_client


def pytest_addoption(parser):
    """Add the --keepalive option for docker services."""

    parser.addoption("--keepalive", "-K", action="store_true", default=False, help="Keep docker services alive")


@pytest.fixture(scope="session")
def keepalive(request):
    """Check if user asked to keep docker services running after the test."""
    return request.config.option.keepalive


@pytest.fixture(scope="session")
def docker_compose_project_name(keepalive, docker_compose_project_name):
    """Override `docker_compose_project_name` if keepalive is set.

    This ensures that we have a unique project name if user asked to keep containers alive.
    """
    if keepalive:
        return "pytest-elasticsearch-native-realm-operator"

    return docker_compose_project_name


@pytest.fixture(scope="session")
def docker_cleanup(keepalive, docker_cleanup):
    """Override cleanup step if keepalive is set.

    If user asked to keep services alive, make `pytest-docker` execute the
    `docker-compose version` command instead. This way, the services won’t
    be shut down.
    """

    if keepalive:
        return "version"

    return docker_cleanup


@pytest.fixture(scope="session")
def docker_compose_file():
    return (Path(__file__).parent / "cluster" / "docker-compose.yaml").resolve()


@pytest.fixture(scope="session")
def kubeconfig(docker_services, keepalive):
    """Wait for kubeconfig to be generated."""
    KUBECONFIG_PATH = (Path(__file__).parent / "cluster" / "kubeconfig.yaml").resolve()
    docker_services.wait_until_responsive(
        check=KUBECONFIG_PATH.exists,
        timeout=10,
        pause=1,
    )
    try:
        yield KUBECONFIG_PATH
    finally:
        if not keepalive:
            os.remove(KUBECONFIG_PATH)


@pytest.fixture(scope="session", autouse=True)
def _validate_kubeconfig(kubeconfig: Path):
    del kubeconfig
    result = subprocess.run(
        "kubectl config view".split(" "),
        capture_output=True,
        check=True,
    )
    config = yaml.load(result.stdout.decode("utf-8"), Loader=yaml.Loader)
    assert len(config["clusters"]) == 1, (
        "Expect a single cluster configured in kubeconfig - is KUBECONFIG env var set?"
    )
    assert config["clusters"][0]["cluster"]["server"] == "https://127.0.0.1:16443", (
        "kubeconfig is pointing to an unexpected cluster"
    )


@pytest.fixture(scope="session", autouse=True)
def wait_for_services(docker_services: Services, kubeconfig: Path, docker_ip: str, _validate_kubeconfig: None):
    """Wait for cluster and resources to be ready."""
    docker_services.wait_until_responsive(
        check=lambda: cluster_is_ready(kubeconfig),
        timeout=90,
        pause=1,
    )
    docker_services.wait_until_responsive(
        check=elasticsearch_is_ready,
        timeout=90.0,
        pause=1,
    )


def cluster_is_ready(kubeconfig: Path):
    """Check if the cluster is ready.

    If its ready, wait for traefik to be ready inside the cluster.
    """
    try:
        subprocess.run(
            [
                "kubectl",
                "wait",
                "--namespace=kube-system",
                "--selector=app.kubernetes.io/instance=traefik",
                "--for=condition=ready",
                "pod",
                "--timeout=90s",
            ],
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def elasticsearch_is_ready():
    client = elasticsearch_client()
    try:
        client.cluster.health(wait_for_status='yellow')
        return True
    except (elasticsearch.ConnectionError, elasticsearch.ConnectionTimeout) as exc:
        print(exc)
        return False
