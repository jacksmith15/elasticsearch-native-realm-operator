import base64
from typing import Optional
from uuid import uuid4

import kopf
from elasticsearch import NotFoundError
from pydantic import ValidationError

from elasticsearch_native_realm_operator.client import elasticsearch_client, kubernetes_client
from elasticsearch_native_realm_operator.models import ElasticsearchNativeRealmUser, ElasticsearchNativeRealmUserSpec


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    # Only send ERROR logs as events:
    # settings.posting.enabled = logging.ERROR
    # Set the finalizer annotation:
    settings.persistence.finalizer = "elasticsearchnativerealm.ckpd.co/finalizer"


@kopf.on.create("elasticsearchnativerealmusers")
@kopf.on.resume("elasticsearchnativerealmusers")
@kopf.on.update("elasticsearchnativerealmusers")
def put_user(body, namespace, **kwargs):
    user = parse_user_resource(body)

    client = elasticsearch_client()
    existing_user = get_existing_user(user.spec.username)

    if existing_user == user.spec:
        print(f"User {user.spec.username!r} already up-to-date")
        return

    if existing_user and existing_user.managed_by != user.spec.managed_by:
        raise kopf.PermanentError(f"User {user.spec.username!r} already exists and is not managed by this resource.")

    validate_roles(user.spec)
    action = "Creat" if not existing_user else "Updat"
    print(f"{action}ing user {user.spec.username!r}")

    body = user.spec.dict()
    username = body.pop("username")
    if not existing_user:
        # Only generate the password and secret if the user doesn't already exist in Elasticsearch.
        body["password"] = create_credentials_secret(username=username, namespace=namespace)
    client.security.put_user(username, body)
    print(f"Successfully {action}ed user {username!r}")


@kopf.on.delete("elasticsearchnativerealmusers")
def delete_user(body, **kwargs):
    user = parse_user_resource(body)

    client = elasticsearch_client()
    existing_user = get_existing_user(user.spec.username)
    if not existing_user:
        print(f"User {user.spec.username!r} already deleted")
        return

    if existing_user.managed_by != user.spec.managed_by:
        print(f"Cannot delete user {user.spec.username!r} as it is not managed by this resource.")
        return

    client.security.delete_user(user.spec.username)
    print(f"Successfully deleted user {user.spec.username!r}")


def create_credentials_secret(username: str, namespace: str) -> str:
    """Create and adopt a secret containing the credentials.

    Adoption ensures that the secret is removed when the user resource is.
    """
    client = kubernetes_client()
    password = str(uuid4())
    body = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": f"elasticsearch-credentials-{username}", "namespace": namespace},
        "type": "Opaque",
        "data": {
            "username": base64.b64encode(username.encode()).decode(),
            "password": base64.b64encode(password.encode()).decode(),
        },
    }
    kopf.adopt(body)
    client.create_namespaced_secret(
        namespace=namespace,
        body=body,
    )
    return password


def parse_user_resource(body: dict) -> ElasticsearchNativeRealmUser:
    try:
        user = ElasticsearchNativeRealmUser(**body)
    except ValidationError as exc:
        raise kopf.PermanentError(f"ElasticsearchNativeRealmUser is incorrectly defined: {exc}")
    # Mark user as managed by the operator.
    user.set_managed_by()
    return user


def get_existing_user(username: str) -> Optional[ElasticsearchNativeRealmUserSpec]:
    client = elasticsearch_client()
    try:
        result = client.security.get_user(username=username)
    except NotFoundError:
        return None
    return ElasticsearchNativeRealmUserSpec(**result[username])


def validate_roles(user_spec: ElasticsearchNativeRealmUserSpec):
    client = elasticsearch_client()
    if not user_spec.roles:
        return
    try:
        roles = client.security.get_role(name=",".join(user_spec.roles))
    except NotFoundError:
        raise kopf.TemporaryError(f"User {user_spec.username!r} has invalid roles: {user_spec.roles}")
    invalid_roles = set(user_spec.roles) - set(roles)
    if invalid_roles:
        raise kopf.TemporaryError(f"User {user_spec.username!r} has invalid roles: {invalid_roles}")
