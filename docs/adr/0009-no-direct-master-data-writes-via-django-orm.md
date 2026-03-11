# ADR-0009: No direct master-data writes via Django ORM

## Status
Accepted

## Context
Локальная запись Category/Unit/Item через ORM нарушает разделение ответственности с SyncServer.

## Decision
Новые сценарии create/update/deactivate для catalog master-data выполняются только через SyncServer admin endpoints.

## Consequences
- Django ORM catalog models не используются как write source для мастер-данных.
- Возможна временная сохранность legacy моделей как transitional compatibility layer.
- Требуется наблюдение за доступностью SyncServer.

## Alternatives Considered
- Смешанная модель (ORM + API) для одних и тех же сущностей (отклонено).
