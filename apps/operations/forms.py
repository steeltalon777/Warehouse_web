from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from django import forms
from django.core.exceptions import ValidationError

QTY_SCALE = Decimal("0.001")


class OperationCreateForm(forms.Form):
    draft_payload = forms.CharField(widget=forms.HiddenInput())

    def clean_draft_payload(self) -> str:
        raw_payload = (self.cleaned_data.get("draft_payload") or "").strip()
        if not raw_payload:
            raise ValidationError("Соберите операцию перед отправкой.")

        try:
            parsed = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise ValidationError("Черновик операции повреждён. Обновите страницу и попробуйте снова.") from exc

        if not isinstance(parsed, dict):
            raise ValidationError("Некорректный формат черновика операции.")

        self.parsed_payload = parsed
        return raw_payload


# ------------------------------------------------------------------
# Acceptance submit helpers
# ------------------------------------------------------------------


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).strip().replace(",", ".")).quantize(QTY_SCALE)
    except (InvalidOperation, ValueError):
        return None


def _serialize_decimal(value: Decimal) -> str:
    return format(value.normalize(), "f")


def validate_acceptance_lines(
    raw_lines: list[dict[str, Any]],
    *,
    remaining_by_line: dict[int | str, Decimal],
) -> list[dict[str, Any]]:
    """
    Validate and build payload for accept-lines.

    Args:
        raw_lines: List of dicts with keys: line_id, accepted_qty, lost_qty, note.
        remaining_by_line: Dict mapping operation line ID -> remaining_qty (from backend).

    Returns:
        List of validated line payloads (only changed lines).

    Raises:
        ValidationError: On any validation failure with per-line detail.
    """
    if not raw_lines:
        raise ValidationError("Не передано ни одной строки для приёмки.")

    payload_lines: list[dict[str, Any]] = []
    errors: list[str] = []

    for raw in raw_lines:
        line_id = raw.get("line_id") or raw.get("operation_line_id") or raw.get("line_number")
        line_label = raw.get("line_number") or line_id
        if line_id is None:
            errors.append("Строка без номера.")
            continue

        accepted_qty = _to_decimal(raw.get("accepted_qty") or 0) or Decimal("0")
        lost_qty = _to_decimal(raw.get("lost_qty") or 0) or Decimal("0")
        note = str(raw.get("note") or "").strip() or None

        if accepted_qty < Decimal("0"):
            errors.append(f"Строка {line_label}: принятое количество не может быть отрицательным.")
            continue
        if lost_qty < Decimal("0"):
            errors.append(f"Строка {line_label}: количество потерь не может быть отрицательным.")
            continue
        if accepted_qty == Decimal("0") and lost_qty == Decimal("0"):
            # Skip unchanged lines
            continue

        remaining = remaining_by_line.get(line_id, Decimal("0"))
        if accepted_qty + lost_qty > remaining:
            errors.append(
                f"Строка {line_label}: сумма принятого ({_serialize_decimal(accepted_qty)}) "
                f"и потерянного ({_serialize_decimal(lost_qty)}) превышает остаток "
                f"({_serialize_decimal(remaining)})."
            )
            continue

        line_payload: dict[str, Any] = {
            "line_id": line_id,
            "accepted_qty": _serialize_decimal(accepted_qty),
            "lost_qty": _serialize_decimal(lost_qty),
        }
        if note:
            line_payload["note"] = note
        payload_lines.append(line_payload)

    if errors:
        raise ValidationError("; ".join(errors))

    return payload_lines


# ------------------------------------------------------------------
# Lost asset resolve helpers
# ------------------------------------------------------------------

LOST_ASSET_ACTIONS = ("found_to_destination", "return_to_source", "write_off")


def validate_lost_asset_resolve(
    raw: dict[str, Any],
    *,
    max_qty: Decimal,
    has_source_site: bool,
) -> dict[str, Any]:
    """
    Validate and build payload for lost asset resolve.

    Args:
        raw: Raw POST data with keys: action, qty, note, responsible_recipient_id.
        max_qty: Maximum quantity that can be resolved.
        has_source_site: Whether the lost asset has a source site.

    Returns:
        Validated payload dict.

    Raises:
        ValidationError: On validation failure.
    """
    action = str(raw.get("action") or "").strip()
    if not action:
        raise ValidationError("Выберите действие для разрешения потери.")
    if action not in LOST_ASSET_ACTIONS:
        raise ValidationError(f"Некорректное действие: {action}.")

    if action == "return_to_source" and not has_source_site:
        raise ValidationError("Возврат на склад-источник недоступен: склад-источник не указан.")

    qty = _to_decimal(raw.get("qty"))
    if qty is None or qty <= Decimal("0"):
        raise ValidationError("Укажите положительное количество для разрешения.")
    if qty > max_qty:
        raise ValidationError(
            f"Количество разрешения ({_serialize_decimal(qty)}) превышает "
            f"доступное ({_serialize_decimal(max_qty)})."
        )

    note = str(raw.get("note") or "").strip() or None
    responsible_recipient_id = raw.get("responsible_recipient_id")

    payload: dict[str, Any] = {
        "action": action,
        "qty": _serialize_decimal(qty),
    }
    if note:
        payload["note"] = note
    if responsible_recipient_id:
        try:
            payload["responsible_recipient_id"] = int(responsible_recipient_id)
        except (TypeError, ValueError):
            raise ValidationError("Некорректный идентификатор получателя.")

    return payload
