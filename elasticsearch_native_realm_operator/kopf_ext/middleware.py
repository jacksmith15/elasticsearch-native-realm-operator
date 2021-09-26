from collections.abc import Callable, Sequence
from functools import reduce, update_wrapper
from typing import Type, Union

import kopf


class Middleware:
    """Base class for implementing operator-wide middleware."""

    def __init__(self, handler: Callable):
        self.handler = handler
        update_wrapper(self, handler)

    def __call__(self, *args, **kwargs):
        return self.handler(*args, **kwargs)

    @staticmethod
    def compile(handler: Callable, middleware: Sequence[Type["Middleware"]]) -> Callable:
        return reduce(lambda inner, outer: outer(inner), [handler] + list(reversed(middleware)))


class StatusStoreMiddleware(Middleware):
    """Middleware which patches results into a status field, based on handler result."""

    def __call__(self, *args, **kwargs):
        patch = kwargs.get("patch")
        if patch is None:
            return self.handler(*args, **kwargs)
        try:
            result = self.handler(*args, **kwargs)
        except Exception as exc:
            self._write_status(patch, exception=exc)
            raise exc
        else:
            self._write_status(patch)
            return result

    @staticmethod
    def _write_status(patch: kopf.Patch, exception: Union[Exception, Type[Exception]] = None):
        exception_type = type(exception) if not isinstance(exception, type) else exception
        patch.status["reconciliation"] = {
            "success": not exception,
            "message": "success" if not exception else str(exception),
            "error": None if not exception else {
                "type": exception_type.__name__,
                "message": str(exception),
                "retry": exception_type is not kopf.PermanentError,
            }
        }
