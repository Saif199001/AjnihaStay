"""Read-only HTTP API boundary for financial reporting and reconciliation."""

from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from workspaces.permissions import WorkspaceStaffPermission

from .reconciliation import ledger_reconciliation_report
from .reporting import (
    advance_credit_report,
    adjustment_report,
    aging_report,
    collection_period_report,
    invoice_financial_report,
    invoice_status_report,
    late_fee_report,
    receivables_report,
    workspace_collection_summary,
    workspace_ledger_activity,
)


def _validation_message(exc):
    return exc.messages[0] if getattr(exc, "messages", None) else str(exc)


def _query_date(request, name, required=True):
    value = request.query_params.get(name)
    if value is None:
        if required:
            raise ValidationError(f"{name} is required")
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid {name} date")


def _query_int(request, name):
    value = request.query_params.get(name)
    if value is None:
        raise ValidationError(f"{name} is required")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"Invalid {name}")


def _json_safe(value):
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _error_response(exc):
    return Response({"error": _validation_message(exc)}, status=400)


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def financial_receivables_report_api(request):
    try:
        as_of = _query_date(request, "as_of", required=False)
        data = receivables_report(workspace=request.workspace, as_of=as_of)
    except ValidationError as exc:
        return _error_response(exc)
    return Response({"data": _json_safe(data)})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def financial_invoice_report_api(request):
    try:
        invoice_id = _query_int(request, "invoice_id")
        data = invoice_financial_report(workspace=request.workspace, invoice_id=invoice_id)
    except ValidationError as exc:
        return Response({"error": _validation_message(exc)}, status=404 if "not found" in str(exc).lower() else 400)
    return Response({"data": _json_safe(data)})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def financial_invoice_status_report_api(request):
    return Response({"data": _json_safe(invoice_status_report(workspace=request.workspace))})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def financial_collection_period_report_api(request):
    try:
        start = _query_date(request, "start")
        end = _query_date(request, "end")
        data = collection_period_report(workspace=request.workspace, start=start, end=end)
    except ValidationError as exc:
        return _error_response(exc)
    return Response({"data": _json_safe(data)})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def financial_aging_report_api(request):
    try:
        as_of = _query_date(request, "as_of")
        data = aging_report(workspace=request.workspace, as_of=as_of)
    except ValidationError as exc:
        return _error_response(exc)
    return Response({"data": _json_safe(data)})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def financial_advance_credit_report_api(request):
    return Response({"data": _json_safe(advance_credit_report(workspace=request.workspace))})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def financial_adjustment_report_api(request):
    return Response({"data": _json_safe(adjustment_report(workspace=request.workspace))})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def financial_late_fee_report_api(request):
    return Response({"data": _json_safe(late_fee_report(workspace=request.workspace))})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def financial_ledger_activity_api(request):
    try:
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        if start:
            start = datetime.fromisoformat(start)
        if end:
            end = datetime.fromisoformat(end)
        if start and end and start > end:
            raise ValidationError("Start cannot be after end")
        entries = workspace_ledger_activity(workspace=request.workspace, start=start, end=end)
        data = [
            {
                "id": entry.pk,
                "event_type": entry.event_type,
                "event_key": entry.event_key,
                "occurred_at": entry.occurred_at,
                "amount": entry.amount,
                "currency": entry.currency,
                "invoice_id": entry.invoice_id,
                "payment_id": entry.payment_id,
                "occupancy_id": entry.occupancy_id,
                "created_by_id": entry.created_by_id,
                "metadata": entry.metadata,
            }
            for entry in entries
        ]
    except (ValidationError, ValueError) as exc:
        return _error_response(exc)
    return Response({"data": _json_safe(data)})


@api_view(["GET"])
@permission_classes([WorkspaceStaffPermission])
def financial_reconciliation_report_api(request):
    return Response({"data": _json_safe(ledger_reconciliation_report(workspace=request.workspace))})
