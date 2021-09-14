from invoke import Collection

from tasks.changelog_check import changelog_check
from tasks.lint import lint
from tasks.local import local
from tasks.release import build, push, release
from tasks.run import run
from tasks.test import coverage, test
from tasks.typecheck import typecheck
from tasks.verify import verify

namespace = Collection(
    build,
    push,
    changelog_check,
    coverage,
    lint,
    release,
    run,
    test,
    typecheck,
    verify,
    local,
)
