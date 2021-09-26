# elasticsearch-native-realm-operator

Kubernetes operator for managing Elasticsearch native realm users.

See [deploy/](./deploy) for a local deployment demo.

## TODO
- [ ] Allow passing `hashed_password` in the CRD (or maybe pre-created secrets)
- [ ] Validating webhook for username change (or maybe use `metadata.name` instead?)
- [ ] Allow regenerating password
- [ ] Allow adoption?
- [ ] Selector for users/roles

## Installation

This project is not currently packaged and so must be installed manually.

Clone the project with the following command:
```
git clone https://github.com/jacksmith15/elasticsearch-native-realm-operator.git
```

## Development

Install dependencies:

```shell
pyenv shell 3.9.4  # Or other 3.9.x
pre-commit install  # Configure commit hooks
poetry install  # Install Python dependencies
```

Run tests:

```shell
poetry run inv verify
```

# License
This project is distributed under the MIT license.
