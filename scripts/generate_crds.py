import sys

import yaml

from elasticsearch_native_realm_operator import main
from elasticsearch_native_realm_operator.kopf_ext import CustomResource


_RESOURCE_DEFINITIONS = [
    model for model in vars(main).values() if isinstance(model, type) and issubclass(model, CustomResource)
]

if __name__ == "__main__":
    sys.stdout.write(
        yaml.dump_all([resource.definition() for resource in _RESOURCE_DEFINITIONS])
    )
