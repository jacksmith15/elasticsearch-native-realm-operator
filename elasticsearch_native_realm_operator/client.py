from functools import cache

import kubernetes
from elasticsearch import Elasticsearch

from elasticsearch_native_realm_operator.config import get_settings


@cache
def elasticsearch_client() -> Elasticsearch:
    config = get_settings()
    return Elasticsearch(config.parsed_elasticsearch_hosts)


@cache
def kubernetes_client() -> kubernetes.client.CoreV1Api:
    return kubernetes.client.CoreV1Api()
