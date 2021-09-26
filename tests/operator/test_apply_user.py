import base64
import subprocess
import time
from collections.abc import Callable
from copy import deepcopy
from typing import Type

import elasticsearch
import kubernetes
import pytest

from elasticsearch_native_realm_operator.config import Settings
from elasticsearch_native_realm_operator.client import elasticsearch_client, kubernetes_client
from tests.utils import kubectl


def make_user(name: str, **kwargs):
    secret_name = kwargs.pop("secret_name", f"elasticsearch-{name}-credentials")
    return {
        "apiVersion": "elasticsearchnativerealm.ckpd.co/v1",
        "kind": "ElasticsearchNativeRealmUser",
        "metadata": {"namespace": "native-realm", "name": name},
        "spec": {
            "secretName": secret_name,
            "user": {
                "username": name,
                "roles": ["viewer"],
                "email": f"{name}@example.com",
                **kwargs,
            },
        },
    }


def wait_for(getter: Callable, retry_on: tuple[Type[Exception], ...], timeout: float = 10.0, pause: float = 1.0):
    start = time.monotonic()
    while True:
        try:
            return getter()
        except retry_on as exc:
            if time.monotonic() - start > timeout:
                raise exc
            time.sleep(pause)


class TestCreateUser:
    @staticmethod
    def should_create_a_new_user_in_elasticsearch(namespace):
        username = "custom-user"
        secret_name = "elasticsearch-custom-user-credentials"
        # WHEN I apply a new elasticsearch user
        kubectl.apply(make_user(username, secret_name=secret_name))
        # THEN a corresponding user should be created in elasticsearch
        client = elasticsearch_client()
        user = wait_for(
            lambda: client.security.get_user(username=username),
            retry_on=elasticsearch.NotFoundError,
        )
        assert user == {
            "custom-user": {
                "username": "custom-user",
                "roles": ["viewer"],
                "full_name": None,
                "email": "custom-user@example.com",
                "metadata": {
                    "elasticsearchnativerealm.ckpd.co/managed-by": (
                        "native-realm:ElasticsearchNativeRealmUser/custom-user"
                    )
                },
                "enabled": True,
            }
        }
        # AND a corresponding secret should be created for the generated credentials
        secret = kubernetes_client().read_namespaced_secret(
            namespace=namespace,
            name=secret_name,
        )
        decoded = {key: base64.b64decode(value.encode()).decode() for key, value in secret.data.items()}
        assert set(decoded) == {"username", "password"}
        assert decoded["username"] == username
        # AND the credentials in the secret can be used to authenticate with Elasticsearch
        user_client = elasticsearch.Elasticsearch(
            hosts=Settings(
                elasticsearch_username=decoded["username"], elasticsearch_password=decoded["password"]
            ).parsed_elasticsearch_hosts
        )
        assert user_client.security.authenticate()

    @staticmethod
    def should_fail_create_on_malformed_user():
        # GIVEN a user which is missing a username
        user = make_user("custom-user-malformed")
        del user["spec"]["user"]["username"]
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            # WHEN I apply the user
            kubectl.apply(user)
        # THEN the apply should fail with a useful error message
        assert (
            exc_info.value.stderr.strip()
            == 'The ElasticsearchNativeRealmUser "custom-user-malformed" is invalid: spec.user.username: Required value'
        )

    @staticmethod
    def should_fail_create_with_undefined_role():
        # GIVEN a user with a role which does not exist in elasticsearch
        username = "custom-user-undefined-role"
        user = make_user(username, roles=["notarole"])
        # WHEN the user is applied
        kubectl.apply(user)
        # THEN a failed apply should be marked on the resource
        status = wait_for(
            lambda: fetch_user_resource(username)["status"]["reconciliation"],
            retry_on=KeyError,
        )
        assert not status["success"]
        # AND the resource should be marked for retry, in case the role was added simultaneously
        assert status["message"] == f"User {username!r} has invalid roles: {set(['notarole'])}"
        assert status["error"]["retry"]

    @staticmethod
    def should_fail_create_for_existing_unmanaged_user():
        # GIVEN a user which already exists in elasticsearch
        username = "custom-user-existing"
        user = make_user(username)
        es_user = user["spec"]["user"].copy()
        del es_user["username"]
        es_user["password"] = "changeme"
        elasticsearch_client().security.put_user(username=username, body=es_user)
        # WHEN the user is applied
        kubectl.apply(user)
        # THEN a failed apply should be marked on the resource
        status = wait_for(
            lambda: fetch_user_resource(username)["status"]["reconciliation"],
            retry_on=KeyError,
            timeout=10,
        )
        assert not status["success"]
        assert status["message"] == f"User {username!r} already exists and is not managed by this resource."
        assert not status["error"]["retry"]


class TestUpdateUser:
    @staticmethod
    @pytest.fixture(autouse=True)
    def user(namespace):
        # GIVEN a user has already been created
        username = "custom-user-modify"
        user = make_user(username)
        kubectl.apply(user)
        client = elasticsearch_client()
        wait_for(
            lambda: client.security.get_user(username=username),
            retry_on=elasticsearch.NotFoundError,
        )
        try:
            yield user
        finally:
            kubectl.delete(user)

    @staticmethod
    @pytest.fixture()
    def username(user):
        return user["spec"]["user"]["username"]

    @staticmethod
    @pytest.fixture()
    def original_secret(user, namespace):
        return kubernetes_client().read_namespaced_secret(
            namespace=namespace,
            name=user["spec"]["secretName"],
        )

    @staticmethod
    def should_modify_user_details(user, username, namespace, original_secret):
        # WHEN the user email is modified
        new_email = "new-email@example.com"
        user = user.copy()
        user["spec"]["user"]["email"] = new_email
        kubectl.apply(user)
        # THEN the user should be updated in elasticsearch
        def assert_updated():
            assert elasticsearch_client().security.get_user(username=username)[username]["email"] == new_email
        wait_for(
            assert_updated,
            retry_on=(AssertionError, KeyError, elasticsearch.NotFoundError)
        )
        # AND the secret should not have changed
        secret = kubernetes_client().read_namespaced_secret(
            namespace=namespace,
            name=user["spec"]["secretName"]
        )
        assert secret == original_secret

    def should_fail_on_update_username(user, username):
        # WHEN the username is modified
        patched = deepcopy(user)
        patched["spec"]["user"]["username"] = "modified-username"
        kubectl.apply(patched)
        # THEN a failed apply should be marked on the resource
        wait_for(
            lambda: fetch_user_resource(username)["status"]["reconciliation"]["error"]["type"],
            retry_on=KeyError
        )
        status = fetch_user_resource(username)["status"]["reconciliation"]
        assert not status["success"]
        assert status["message"] == "Cannot change username once created."
        assert not status["error"]["retry"]
        # AND a revert to the original state should be successful
        kubectl.apply(user)
        time.sleep(10)
        status = fetch_user_resource(username)["status"]["reconciliation"]
        assert status["success"], status

    @staticmethod
    def should_fail_on_update_secret_name():
        assert False

    @staticmethod
    def should_succeed_on_revert_updated_username():
        assert False

    @staticmethod
    def should_succeed_on_revert_updated_secret_name():
        assert False


class TestDeleteUser:
    @staticmethod
    @pytest.fixture(autouse=True)
    def user(namespace):
        # GIVEN a user has already been created
        username = "custom-user-modify"
        user = make_user(username)
        kubectl.apply(user)
        client = elasticsearch_client()
        wait_for(
            lambda: client.security.get_user(username=username),
            retry_on=elasticsearch.NotFoundError,
        )
        return user

    @staticmethod
    @pytest.fixture()
    def username(user):
        return user["spec"]["user"]["username"]

    @staticmethod
    def should_delete_managed_user(user, username):
        assert False

    @staticmethod
    def should_delete_failed_user():
        assert False

    @staticmethod
    def should_preserve_unmanaged_es_user():
        assert False

    @staticmethod
    def should_successfully_delete_a_nonexistent_user():
        assert False


def fetch_user_resource(username: str) -> dict:
    return kubernetes.client.CustomObjectsApi().get_namespaced_custom_object(
        group="elasticsearchnativerealm.ckpd.co",
        version="v1",
        namespace="native-realm",
        plural="elasticsearchnativerealmusers",
        name=username,
    )
