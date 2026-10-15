"""Scoped authority for canonical Leasing model writes."""
from contextlib import contextmanager
from contextvars import ContextVar

from django.core.exceptions import ValidationError

_ACTIVE_CANONICAL_WRITES = ContextVar("leasing_active_canonical_writes", default=frozenset())


@contextmanager
def canonical_write(model_name, operation):
    active = _ACTIVE_CANONICAL_WRITES.get()
    token = _ACTIVE_CANONICAL_WRITES.set(active | {(model_name, operation)})
    try:
        yield
    finally:
        _ACTIVE_CANONICAL_WRITES.reset(token)


def is_canonical_mutation(model_name, operation):
    return (model_name, operation) in _ACTIVE_CANONICAL_WRITES.get()


def require_canonical_mutation(model_name, operation):
    if not is_canonical_mutation(model_name, operation):
        raise ValidationError(f"{model_name} {operation} requires an active canonical service context")
