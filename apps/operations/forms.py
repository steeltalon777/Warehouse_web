from __future__ import annotations

import json

from django import forms
from django.core.exceptions import ValidationError


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
