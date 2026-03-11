# ADR-0005: HTTP integration with external SyncServer API

## Status
Accepted

## Context
Warehouse_web работает как web-клиент в экосистеме, где внешний SyncServer (FastAPI) является системным backend для части данных/операций.

## Decision
Интеграцию выполнять по HTTP через `httpx`-клиенты с базовым URL из `SYNC_SERVER_URL`.

## Consequences
Плюсы:
- Явная граница между UI-клиентом и внешним backend.
- Простая замена endpoint/окружений через конфигурацию.

Минусы:
- Появляется зависимость от сетевой доступности внешнего API.
- Нужна аккуратная обработка ошибок/таймаутов и ретраев (по мере роста интеграций).

## Alternatives Considered
### Option 1: Прямой доступ к общей БД
Сильная связность и потеря границ между системами.

### Option 2: Message broker / async integration first
Сложнее для начального этапа, избыточно для текущего объема интеграции.
