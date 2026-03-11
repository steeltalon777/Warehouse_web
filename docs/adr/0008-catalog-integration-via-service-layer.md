# ADR-0008: Catalog integration through service + SyncServer client layer

## Status
Accepted

## Context
Прямой HTTP-код во view-слое усложняет поддержку и единообразную обработку ошибок.

## Decision
Ввести единый клиент `apps/integration/syncserver_client.py` и сервис оркестрации `apps/catalog/services.py`. Views/forms используют только сервисный слой.

## Consequences
- Тонкий view-слой.
- Единая обработка ошибок 400/404/409/5xx.
- Легче тестировать интеграционную логику.

## Alternatives Considered
- HTTP вызовы непосредственно из views (отклонено).
- Дублирование клиентов по apps (отклонено).
