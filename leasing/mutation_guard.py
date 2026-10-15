"""Scoped authority for canonical Leasing model writes.

Only the canonical service modules listed below may open a write context.
Model save flags are not authority on their own; the caller module is checked
before the context is activated.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import inspect

from django.core.exceptions import ValidationError


_ACTIVE_CANONICAL_WRITES = ContextVar("leasing_active_canonical_writes", default=frozenset())

_ALLOWED_WRITERS = {
    ("lease", "create"): {"leasing.lease_service"},
    ("lease", "update"): {"leasing.lease_service"},
    ("lease", "lifecycle"): {
        "leasing.lease_service",
        "leasing.cancellation_service",
        "leasing.expiry_service",
        "leasing.termination_service",
    },
    ("notice", "create"): {"leasing.notice_service"},
    ("notice", "update"): {"leasing.notice_service"},
    ("notice", "lifecycle"): {"leasing.notice_service"},
    ("renewal", "create"): {"leasing.renewal_service"},
    ("renewal", "update"): {"leasing.renewal_service"},
    ("renewal", "lifecycle"): {"leasing.renewal_service"},
    ("contract_version", "create"): {
        "leasing.lease_service",
        "leasing.renewal_service",
    },
    ("lifecycle_event", "create"): {"leasing.lifecycle_event_service"},
}


@contextmanager
def _activate_canonical_write(model_name, operation):
    active = _ACTIVE_CANONICAL_WRITES.get()
    token = _ACTIVE_CANONICAL_WRITES.set(active | {(model_name, operation)})
    try:
        yield
    finally:
        _ACTIVE_CANONICAL_WRITES.reset(token)


def canonical_write(model_name, operation):
    """Return a write context only to the service authorized for this mutation."""
    caller = inspect.currentframe().f_back
    caller_module = caller.f_globals.get("__name__") if caller else None
    allowed_callers = _ALLOWED_WRITERS.get((model_name, operation), set())
    if caller_module not in allowed_callers:
        raise ValidationError(
            f"{model_name} {operation} write context may only be opened by its canonical service"
        )
    return _activate_canonical_write(model_name, operation)


def is_canonical_mutation(model_name, operation):
    return (model_name, operation) in _ACTIVE_CANONICAL_WRITES.get()


def require_canonical_mutation(model_name, operation):
    if not is_canonical_mutation(model_name, operation):
        raise ValidationError(f"{model_name} {operation} requires an active canonical service context")
