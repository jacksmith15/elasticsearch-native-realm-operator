from collections.abc import Sequence
from typing import ClassVar, Literal, Optional, Type, Union

import kopf
from pydantic import BaseModel, Field, ValidationError, parse_obj_as

from .middleware import Middleware
from .utils import resolve_refs


class CustomResourceDefinitionNames(BaseModel):
    kind: str
    plural: str
    singular: Optional[str]
    categories: Optional[list[str]]
    listKind: Optional[str]
    shortNames: Optional[list[str]]


class CustomResourceDefinitionAdditionalPrinterColumn(BaseModel):
    jsonPath: str
    name: str
    type: Literal["integer", "number", "string", "boolean"]
    description: Optional[str]
    format: Optional[str]
    priority: Optional[int]


class CustomResource(BaseModel):
    scope: ClassVar[str]
    group: ClassVar[str]
    names: ClassVar[CustomResourceDefinitionNames]
    additionalPrinterColumns: ClassVar[list[CustomResourceDefinitionAdditionalPrinterColumn]]

    def __init_subclass__(
        cls,
        *,
        scope: str,
        group: str,
        names: Union[CustomResourceDefinitionNames, dict],
        additionalPrinterColumns: Optional[list[Union[dict, CustomResourceDefinitionAdditionalPrinterColumn]]] = None,
    ):
        cls.scope = scope
        cls.group = group
        cls.names = parse_obj_as(CustomResourceDefinitionNames, names)
        additionalPrinterColumns = additionalPrinterColumns or []
        cls.additionalPrinterColumns = parse_obj_as(
            list[CustomResourceDefinitionAdditionalPrinterColumn], additionalPrinterColumns
        )

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

    @classmethod
    def register(cls, middleware: Sequence[Type[Middleware]] = None):
        """Register any handlers defined on this resource definition."""
        handlers = {
            operation: cls._make_handler(operation)
            for operation in ("create", "update", "delete", "resume")
            if hasattr(cls, operation)
        }
        for operation, handler in handlers.items():
            getattr(kopf.on, operation)(cls.names.kind)(Middleware.compile(handler, middleware or []))

    @classmethod
    def _make_handler(cls, operation: str):
        method = getattr(cls, operation)
        def handle(body, **kwargs):
            try:
                parsed = cls(**body)
            except ValidationError as exc:
                raise kopf.PermanentError(f"Got invalid {cls.kind!r}: {exc}")
            method(parsed, body=body, **kwargs)
        handle.__name__ = handle.__qualname__ = f"handle_{operation}"
        return handle

    @classmethod
    def definition(cls):
        schema = resolve_refs(cls.schema())
        # Kubernetes API does not allow specifying schema annotations for metadata
        schema["properties"]["metadata"] = {
            key: value for key, value in schema["properties"]["metadata"].items() if key == "type"
        }
        return {
            "apiVersion": "apiextensions.k8s.io/v1",
            "kind": "CustomResourceDefinition",
            "metadata": {"name": f"{cls.names.plural}.{cls.group}"},
            "spec": {
                "scope": cls.scope,
                "group": cls.group,
                "names": cls.names.dict(),
                "versions": [
                    {
                        "name": "v1",
                        "served": True,
                        "storage": True,
                        "schema": {"openAPIV3Schema": schema},
                        "additionalPrinterColumns": [col.dict() for col in cls.additionalPrinterColumns],
                    }
                ],
            },
        }

    class Config:
        schema_extra = {"x-kubernetes-preserve-unknown-fields": True}
