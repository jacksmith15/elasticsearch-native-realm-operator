import base64
import logging
from typing import Optional
from uuid import uuid4

import kopf
from elasticsearch import NotFoundError
from pydantic import BaseModel, Field

from elasticsearch_native_realm_operator.client import elasticsearch_client, kubernetes_client
from elasticsearch_native_realm_operator.constants import MANAGED_BY_KEY
from elasticsearch_native_realm_operator.kopf_ext import CustomResource


class ElasticsearchNativeRealmUserSpecUser(BaseModel):
    username: str = Field(..., description="An identifer for the user.", minLength=1, maxLength=1024)
    roles: list[str] = Field(
        ...,
        description=(
            "A set of roles the user has. The roles determine the user's access permissions. "
            "To create a user without any roles, specify and empty list: '[]'."
        ),
    )
    metadata: dict = Field(
        default_factory=dict,
        description=(
            "Arbitrary metadata that you want to associate with the user.  "
            "Note that metadata will be used to track management of the user via the operator."
        ),
    )
    enabled: bool = Field(True, description="Specifies whether the user is enabled. The default value is `true`.")
    email: Optional[str] = Field(description="The email of the user (optional).")
    full_name: Optional[str] = Field(description="The full name of the user (optional).")

    @property
    def managed_by(self) -> Optional[str]:
        return self.metadata.get(MANAGED_BY_KEY, None)

    def set_managed_by(self, namespace: str, kind: str, name: str):
        self.metadata[MANAGED_BY_KEY] = f"{namespace}:{kind}/{name}"


class ElasticsearchNativeRealmUserSpec(BaseModel):
    user: ElasticsearchNativeRealmUserSpecUser
    secretName: str


class ElasticsearchNativeRealmUser(
    CustomResource,
    scope="Namespaced",
    group="elasticsearchnativerealm.ckpd.co",
    names={
        "kind": "ElasticsearchNativeRealmUser",
        "plural": "elasticsearchnativerealmusers",
        "singular": "elasticsearchnativerealmuser",
    },
):
    spec: ElasticsearchNativeRealmUserSpec

    def update(self, namespace: str, logger: logging.Logger, diff: list[tuple], **kwargs):
        user = self.spec.user
        # Mark staged user as managed by this resource:
        user.set_managed_by(
            namespace=self.metadata.get("namespace", "default"),
            kind=self.kind,
            name=self.metadata["name"],
        )

        # Don't allow edits to the username or secret name:
        field_operations = [operation[:2] for operation in diff]
        if ("change", ("spec", "user", "username")) in field_operations:
            raise kopf.PermanentError("Cannot change username once created.")
        if ("change", ("spec", "secretName")) in field_operations:
            raise kopf.PermanentError("Cannot change secret name once created.")

        # Check if user already exists (update):
        current = fetch_user(user.username)
        if current == user:
            logger.info(f"User {user.username!r} already up-to-date.")
            return

        # Ensure this user is managed by this resource (prevents conflicts):
        if current and current.managed_by != user.managed_by:
            raise kopf.PermanentError(
                f"User {user.username!r} already exists and is not managed by this resource."
            )

        # Ensure the roles exist:
        self._validate_roles()

        # Create secret if necessary:
        body = user.dict(exclude_none=True)
        if not current:
            body["password"] = self._create_credentials_secret(namespace)

        # Reconcile with Elasticsearch
        username = body.pop("username")
        elasticsearch_client().security.put_user(username=username, body=body)
        logger.info(f"Successfully reconciled user {username!r}")

    create = resume = update

    def delete(self, namespace: str, logger: logging.Logger, **kwargs):
        user = self.spec.user
        # Mark staged user as managed by this resource:
        user.set_managed_by(
            namespace=self.metadata.get("namespace", "default"),
            kind=self.kind,
            name=self.metadata["name"],
        )

        current = fetch_user(user.username)
        # Ignore if user is already deleted:
        if not current:
            logger.info(f"User {user.username!r} does not exist, not further action needed.")
            return

        # Don't delete if the user isn't managed by this resource:
        if current.managed_by != user.managed_by:
            logger.warning(f"Skipping deletion of user {user.username!r}, as it is not managed by this resource.")
            return

        # Delete the user:
        elasticsearch_client().security.delete_user(username=user.username)
        logger.info(f"Successfully removed user {user.username!r}")

    def _validate_roles(self):
        """Validate that each role specified already exists in Elasticsearch."""
        user = self.spec.user
        client = elasticsearch_client()
        if not user.roles:
            return
        try:
            roles = client.security.get_role(name=",".join(user.roles))
        except NotFoundError:
            roles = {}
        invalid_roles = set(user.roles) - set(roles)
        if invalid_roles:
            # Temporary error means this will be retried, as the role might have been added at the same time.
            raise kopf.TemporaryError(f"User {user.username!r} has invalid roles: {invalid_roles}")

    def _create_credentials_secret(self, namespace: str):
        """Create and adopt a secret containing the credentials.

        Adoption ensures that the secret is removed when the user resource is.
        """
        user = self.spec.user
        client = kubernetes_client()
        password = str(uuid4())
        body = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": self.spec.secretName, "namespace": namespace},
            "type": "Opaque",
            "data": {
                "username": base64.b64encode(user.username.encode()).decode(),
                "password": base64.b64encode(password.encode()).decode(),
            },
        }
        kopf.adopt(body)
        client.create_namespaced_secret(
            namespace=namespace,
            body=body,
        )
        return password


def fetch_user(username: str) -> Optional[ElasticsearchNativeRealmUserSpecUser]:
    client = elasticsearch_client()
    try:
        result = client.security.get_user(username=username)
    except NotFoundError:
        return None
    return ElasticsearchNativeRealmUserSpecUser(**result[username])
