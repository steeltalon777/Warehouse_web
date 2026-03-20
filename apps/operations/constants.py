from __future__ import annotations


OPERATION_TYPE_META: tuple[dict[str, object], ...] = (
    {
        "code": "RECEIVE",
        "label": "Приход",
        "description": "Поступление ТМЦ на склад.",
        "enabled": True,
        "single_site_label": "Склад",
        "requires_recipient": False,
        "notes_label": "Комментарий",
        "allow_negative_qty": False,
    },
    {
        "code": "EXPENSE",
        "label": "Расход",
        "description": "Списание со склада на внешнего получателя.",
        "enabled": True,
        "single_site_label": "Склад",
        "requires_recipient": True,
        "notes_label": "Комментарий",
        "allow_negative_qty": False,
    },
    {
        "code": "MOVE",
        "label": "Перемещение",
        "description": "Перемещение между складами.",
        "enabled": True,
        "single_site_label": "",
        "requires_recipient": False,
        "notes_label": "Комментарий",
        "allow_negative_qty": False,
    },
    {
        "code": "WRITE_OFF",
        "label": "Списание",
        "description": "Списание ТМЦ по основанию.",
        "enabled": True,
        "single_site_label": "Склад",
        "requires_recipient": False,
        "notes_label": "Основание",
        "allow_negative_qty": False,
    },
    {
        "code": "ADJUSTMENT",
        "label": "Корректировка",
        "description": "Ручная корректировка остатков.",
        "enabled": True,
        "single_site_label": "Склад",
        "requires_recipient": False,
        "notes_label": "Комментарий",
        "allow_negative_qty": True,
    },
    {
        "code": "ISSUE",
        "label": "Выдача",
        "description": "Тип виден в интерфейсе, но подтверждение пока не реализовано.",
        "enabled": False,
        "single_site_label": "Склад",
        "requires_recipient": True,
        "notes_label": "Комментарий",
        "allow_negative_qty": False,
    },
    {
        "code": "ISSUE_RETURN",
        "label": "Возврат выдачи",
        "description": "Тип виден в интерфейсе, но подтверждение пока не реализовано.",
        "enabled": False,
        "single_site_label": "Склад",
        "requires_recipient": True,
        "notes_label": "Комментарий",
        "allow_negative_qty": False,
    },
)

OPERATION_TYPE_LABELS = {str(item["code"]): str(item["label"]) for item in OPERATION_TYPE_META}

OPERATION_STATUS_META = {
    "draft": {"label": "Черновик", "tone": "muted"},
    "created": {"label": "Создана", "tone": "info"},
    "pending": {"label": "Ожидает подтверждения", "tone": "warning"},
    "submitted": {"label": "Подтверждена", "tone": "success"},
    "rejected": {"label": "Отклонена", "tone": "danger"},
    "cancelled": {"label": "Отменена", "tone": "danger"},
}

CREATE_DISABLED_OPERATION_TYPES = {
    str(item["code"]) for item in OPERATION_TYPE_META if not bool(item["enabled"])
}
