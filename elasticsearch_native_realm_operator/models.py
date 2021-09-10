from typing import Optional

from pydantic import BaseModel, Field

_MANAGED_BY_KEY = "elasticsearchnativerealm.ckpd.co/managed-by"


class ElasticsearchNativeRealmUserSpec(BaseModel):
    username: str
    roles: list[str]
    metadata: dict = Field(default_factory=dict)
    enabled: bool = True
    email: Optional[str]
    full_name: Optional[str]

    @property
    def managed_by(self) -> Optional[str]:
        return self.metadata.get(_MANAGED_BY_KEY, None)


class ElasticsearchNativeRealmUser(BaseModel):
    apiVersion: str
    kind: str
    metadata: dict
    spec: ElasticsearchNativeRealmUserSpec

    def set_managed_by(self):
        self.spec.metadata[_MANAGED_BY_KEY] = f"{self.metadata['namespace']}:{self.kind}/{self.metadata['name']}"
