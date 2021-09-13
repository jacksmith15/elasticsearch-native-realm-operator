import kopf
from jsonpointer import JsonPointer
from pydantic import BaseModel, Field, ValidationError


class CustomResource(BaseModel):
    def __init_subclass__(
        cls,
        *,
        scope: str,
        group: str,
        kind: str,
        singular: str,
        plural: str,
    ):
        cls.scope = scope
        cls.group = group
        cls.kind = kind
        cls.singular = singular
        cls.plural = plural

    apiVersion: str = Field(
        ...,
        description="""APIVersion defines the versioned schema of this representation
of an object. Servers should convert recognized schemas to the latest
internal value, and may reject unrecognized values.
More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#resources
""".replace(
            "\n", " "
        ),
    )
    kind: str = Field(
        ...,
        description="""Kind is a string value representing the REST resource this
object represents. Servers may infer this from the endpoint the client
submits requests to. Cannot be updated. In CamelCase.
More info: https://git.k8s.io/community/contributors/devel/sig-architecture/api-conventions.md#types-kinds
""".replace(
            "\n", " "
        ),
    )
    metadata: dict = Field(
        default_factory=dict,
        description="""Metadata that all persisted resources must have, including name and namespace.
More info: https://kubernetes.io/docs/reference/kubernetes-api/common-definitions/object-meta/
""".replace(
            "\n", " "
        ),
    )

    def create(self, **kwargs):
        ...

    def update(self, **kwargs):
        ...

    def delete(self, **kwargs):
        ...

    def resume(self, **kwargs):
        ...

    @classmethod
    def register(cls):
        for operation in ("create", "update", "delete", "resume"):

            def handle(body, **kwargs):
                try:
                    parsed = cls(**body)
                except ValidationError as exc:
                    raise kopf.PermanentError(f"Got invalid {cls.kind!r}: {exc}")
                getattr(parsed, operation)(body=body, **kwargs)

            handle.__name__ = handle.__qualname__ = f"handle_{operation}"
            getattr(kopf.on, operation)(handle)

    @classmethod
    def definition(cls):
        return {
            "apiVersion": "apiextensions.k8s.io/v1",
            "kind": "CustomResourceDefinition",
            "metadata": {"name": f"{cls.plural}.{cls.group}"},
            "spec": {
                "scope": cls.scope,
                "group": cls.group,
                "names": {
                    "kind": cls.kind,
                    "plural": cls.plural,
                    "singular": cls.singular,
                },
                "versions": [
                    {
                        "name": "v1",
                        "served": True,
                        "storage": True,
                        "schema": {"openAPIV3Schema": _resolve_refs(cls.schema())},
                    }
                ],
            },
        }

    class Config:
        schema_extra = {"x-kubernetes-preserve-unknown-fields": True}


_sentinel = object()


def _resolve_refs(schema: dict, part=_sentinel):
    """ "Resolve references in schema generated by pydantic.

    Does not support remote or cyclical references.
    """
    if part is _sentinel:
        part = schema
    if not isinstance(part, (dict, list)):
        return part
    if isinstance(part, list):
        return [_resolve_refs(schema, item) for item in part]
    if "$ref" in part:
        return _resolve_refs(JsonPointer(part["$ref"].lstrip("#")).resolve(schema))
    return {key: _resolve_refs(schema, value) for key, value in part.items() if key != "definitions"}
