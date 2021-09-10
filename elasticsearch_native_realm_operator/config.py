from functools import cache

from furl import furl
from pydantic import BaseSettings

class Settings(BaseSettings):
    elasticsearch_hosts: list[str]
    elasticsearch_username: str
    elasticsearch_password: str

    @property
    def parsed_elasticsearch_hosts(self) -> list[str]:
        elasticsearch_hosts_with_auth = []
        for host in self.elasticsearch_hosts:
            url = furl(host)
            url.username = self.elasticsearch_username
            url.password = self.elasticsearch_password
            elasticsearch_hosts_with_auth.append(url.tostr())
        return elasticsearch_hosts_with_auth


@cache
def get_settings():
    return Settings()
