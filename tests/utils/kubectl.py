import json
import subprocess
from typing import Optional

import yaml


def get(kind: str, name: str = None, **kwargs) -> Optional[dict]:
    command = f"kubectl get {kind} -o json".split(" ")
    if "namespace" in kwargs:
        namespace = kwargs.pop("namespace")
        if namespace == "all":
            command.append("--all-namespaces")
        else:
            command.extend(["--namespace", namespace])
    if name:
        command.append(name)
    try:
        result = subprocess.run(command, capture_output=True, check=True, encoding="utf-8")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr.strip())
    return json.loads(result.stdout)


def apply(*resources: dict):
    subprocess.run(
        "kubectl apply -f -".split(" "),
        encoding="utf-8",
        input=yaml.dump_all(resources),
        check=True,
        capture_output=True,
    )


def delete(*resources: dict):
    subprocess.run(
        "kubectl delete -f -".split(" "),
        encoding="utf-8",
        input=yaml.dump_all(resources),
        check=True,
        capture_output=True,
    )
