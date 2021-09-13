from typing import Optional

from json_ref_dict import
from pydantic import BaseModel, Field

from elasticsearch_native_realm_operator.framework.models import CustomResource


_MANAGED_BY_KEY = "elasticsearchnativerealm.ckpd.co/managed-by"


class ElasticsearchNativeRealmUserSpec(BaseModel):
    username: str = Field(..., description="An identifer for the user.", minLength=1, maxLength=1024)
    roles: list[str] = Field(
        ...,
        description="A set of roles the user has. The roles determine the user's access permissions. To create a user without any roles, specify and empty list: '[]'.",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Arbitrary metadata that you want to associate with the user.  Note that metadata will be used to track management of the user via the operator.",
    )
    enabled: bool = Field(True, description="Specifies whether the user is enabled. The default value is `true`.")
    email: Optional[str] = Field(description="The email of the user (optional).")
    full_name: Optional[str] = Field(description="The full name of the user (optional).")

    @property
    def managed_by(self) -> Optional[str]:
        return self.metadata.get(_MANAGED_BY_KEY, None)


class ElasticsearchNativeRealmUser(
    CustomResource,
    scope="Namespaced",
    group="elasticsearchnativerealm.ckpd.co",
    kind="ElasticsearchNativeRealmUser",
    plural="elasticsearchnativerealmusers",
    singular="elasticsearchnativerealmuser",
):
    spec: ElasticsearchNativeRealmUserSpec


    def update(self, namespace: str, logger: logging.Logger, diff: list[tuple] **kwargs):
        field_operations = [operation[:2] for operation in diff]
        if ("change", ("spec", "username")) in field_operations:
            raise kopf.PermanentError("Cannot change username once created.")
        current = fetch_user(self.spec.username)
        if current == self.spec:
            # No changes necessary
            return
        if current and current.managed_by != self.spec.managed_by:
            raise kopf.PermanentError(f"User {user.spec.username!r} already exists and is not managed by this resource.")
        self._validate_roles()
        body = self.spec.dict()
        username = body.pop("username")
        if not current:
            body["password"] = self._create_credentials_secret()
        self.client.put_user(username, body)
        logger.info(f"Successfully reconciled user {username!r}")

    create = resume = update

    def delete(self, namespace: str, logger: logging.Logger, **kwargs):
        current = fetch_user(self.spec.username)
        if not current:
            # Nothing to delete
            return
        if existing_user.managed_by != user.spec.managed_by:
            logger.warning(f"Skipping deletion of user {self.spec.username!r}, as it is not managed by this resource.")
            return
        client.security.delete_user(self.spec.username)
        logger.info(f"Successfully removed user {username!r}")

    def _validate_roles(self):
        ...

    def _create_credentials_secret(self):
        ...
