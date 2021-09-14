import logging

import kopf
from elasticsearch_native_realm_operator.resources.role import ElasticsearchNativeRealmRole
from elasticsearch_native_realm_operator.resources.user import ElasticsearchNativeRealmUser


@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    # Only send ERROR logs as events:
    # settings.posting.enabled = logging.ERROR
    # Set the finalizer annotation:
    settings.persistence.finalizer = "elasticsearchnativerealm.ckpd.co/finalizer"
    settings.posting.level = logging.WARNING


ElasticsearchNativeRealmRole.register()
ElasticsearchNativeRealmUser.register()
