# ADR-0006: SyncServer as source of truth for catalog master-data

## Status
Accepted

## Context
Исторически Warehouse_web использовал локальные Django модели `Category`, `Unit`, `Item` как рабочий CRUD-слой. Это создавало риск рассинхронизации с SyncServer.

## Decision
Source of truth по `Category`, `Unit`, `Item` закреплен за SyncServer. Warehouse_web не должен формировать конкурирующую истину в своей ORM.

## Consequences
- Единая доменная истина в backend-сервисе SyncServer.
- UI работает с API-ответами, а не с локальным catalog CRUD.
- Зависимость от доступности SyncServer.

## Alternatives Considered
- Оставить dual-write в локальную БД и SyncServer (отклонено из-за рассинхронизации).
- Полностью локальный каталог в Django (отклонено как нарушение системной роли).
