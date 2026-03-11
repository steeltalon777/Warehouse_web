# ADR-0002: UUID identifiers for catalog domain entities

## Status
Accepted

## Context
Сущности каталога (`Category`, `Unit`, `Item`) являются доменными объектами, потенциально синхронизируемыми с внешними системами.

## Decision
Использовать UUID как primary key для доменных сущностей каталога.

## Consequences
Плюсы:
- Глобально уникальные идентификаторы, удобные для интеграции.
- Меньше конфликтов при потенциальной распределенной синхронизации.

Минусы:
- Менее читабельные идентификаторы в ручной отладке.
- Возможные накладные расходы по сравнению с integer PK.

## Alternatives Considered
### Option 1: Auto-increment integer PK
Проще для человека, но хуже при межсистемном обмене.

### Option 2: Composite business keys
Усложняет связи и миграции.
