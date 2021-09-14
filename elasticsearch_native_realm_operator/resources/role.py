import logging
from typing import Optional

import kopf
from elasticsearch import NotFoundError
from pydantic import BaseModel, Field

from elasticsearch_native_realm_operator.client import elasticsearch_client
from elasticsearch_native_realm_operator.constants import MANAGED_BY_KEY
from elasticsearch_native_realm_operator.kopf_ext import CustomResource


class ElasticsearchNativeRealmRoleApplicationPrivilegeEntry(BaseModel):
    application: str = Field(description="The name of the application to which this entry applies.")
    privileges: list[str] = Field(
        default_factory=list,
        description="A list of strings, where each element is the name of an application privilege or action."
    )
    resources: list[str] = Field(
        default_factory=list,
        description="A list resources to which the privileges are applied."
    )


class ElasticsearchNativeRealmRoleIndicesPermissionsEntry(BaseModel):
    names: list[str] = Field(
        description="A list of indices (or index name patterns) to which the permissions in this entry apply."
    )
    privileges: list[str] = Field(
        description="The index level privileges that the owners of the role have on the specified indices."
    )
    field_security: Optional[dict] = Field(
        description=(
            "The document fields that the owners of the role have read access to. For more information, see "
            "https://www.elastic.co/guide/en/elasticsearch/reference/7.14/field-and-document-access-control.html."
        )
    )
    query: Optional[str] = Field(
        description=(
            "A search query that defines the documents the owners of the role have read access to. A document within "
            "the specified indices must match this query in order for it to be accessible by the owners of the role."
        )
    )


class ElasticsearchNativeRealmRoleSpecRole(BaseModel):
    name: str = Field(description="The name of the role.")
    applications: list[ElasticsearchNativeRealmRoleApplicationPrivilegeEntry] = Field(
        default_factory=list, description="A list of application privilege entries."
    )
    cluster: list[str] = Field(
        default_factory=list,
        description=(
            "A list of cluster privileges. These privileges define the cluster level actions that users with this role "
            "are able to execute."
        ),
    )
    indices: list[ElasticsearchNativeRealmRoleIndicesPermissionsEntry] = Field(
        default_factory=list,
        description="A list of indices permissions entries.",
    )
    metadata: dict = Field(
        default_factory=dict,
        description=(
            "Optional meta-data. Within the metadata object, keys that begin with _ are reserved for system usage. "
            "Note that metadata will be used to track management of the role via the operator."
        ),
    )
    run_as: list[str] = Field(
        default_factory=list,
        description=(
            "A list of users that the owners of this role can impersonate. For more information, see "
            "https://www.elastic.co/guide/en/elasticsearch/reference/7.14/run-as-privilege.html."
        ),
    )

    @property
    def managed_by(self) -> Optional[str]:
        return self.metadata.get(MANAGED_BY_KEY, None)

    def set_managed_by(self, namespace: str, kind: str, name: str):
        self.metadata[MANAGED_BY_KEY] = f"{namespace}:{kind}/{name}"


class ElasticsearchNativeRealmRoleSpec(BaseModel):
    role: ElasticsearchNativeRealmRoleSpecRole


class ElasticsearchNativeRealmRole(
    CustomResource,
    scope="Namespaced",
    group="elasticsearchnativerealm.ckpd.co",
    names={
        "kind": "ElasticsearchNativeRealmRole",
        "plural": "elasticsearchnativerealmroles",
        "singular": "elasticsearchnativerealmrole",
    },
):
    spec: ElasticsearchNativeRealmRoleSpec

    def update(self, logger: logging.Logger, diff: list[tuple], **kwargs):
        role = self.spec.role
        # Mark role as managed by this resource
        role.set_managed_by(
            namespace=self.metadata.get("namespace", "default"),
            kind=self.kind,
            name=self.metadata["name"],
        )

        # Don't allow edits to the role name:
        field_operations = [operation[:2] for operation in diff]
        if ("change", ("spec", "role", "name")) in field_operations:
            raise kopf.PermanentError("Cannot change role name once created.")

        # Check if role already exists (update):
        current = fetch_role(role.name)
        if current == role:
            logger.info(f"Role {role.name!r} already up-to-date.")
            return

        # Ensure this role is managed by this resource (prevents conflicts):
        if current and current.managed_by != role.managed_by:
            raise kopf.PermanentError(
                f"Role {role.name!r} already exists and is not managed by this resource."
            )

        # Reconcile with Elasticsearch
        body = role.dict(exclude_none=True)
        role_name = body.pop("name")
        elasticsearch_client().security.put_role(name=role_name, body=body)
        logger.info(f"Successfully reconciled role {role_name!r}")

    create = resume = update

    def delete(self, namespace: str, logger: logging.Logger, **kwargs):
        role = self.spec.role
        # Mark staged role as managed by this resource:
        role.set_managed_by(
            namespace=self.metadata.get("namespace", "default"),
            kind=self.kind,
            name=self.metadata["name"],
        )

        current = fetch_role(role.name)
        # Ignore if role is already deleted:
        if not current:
            logger.info(f"Role {role.name!r} does not exist, not further action needed.")
            return

        # Don't delete if the role isn't managed by this resource:
        if current.managed_by != role.managed_by:
            logger.warning(f"Skipping deletion of role {role.name!r}, as it is not managed by this resource.")
            return

        # Delete the role:
        elasticsearch_client().security.delete_role(name=role.name)
        logger.info(f"Successfully removed role {role.name!r}")


def fetch_role(name: str) -> Optional[ElasticsearchNativeRealmRoleSpecRole]:
    client = elasticsearch_client()
    try:
        result = client.security.get_role(name=name)
    except NotFoundError:
        return None
    return ElasticsearchNativeRealmRoleSpecRole(name=name, **result[name])
