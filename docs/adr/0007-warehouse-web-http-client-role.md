# ADR-0007: Warehouse_web as privileged HTTP client of SyncServer

## Status
Accepted

## Context
Warehouse_web должен выполнять роль web UI для кладовщиков, но не backend-хранилища мастер-данных.

## Decision
Warehouse_web рассматривается как privileged client SyncServer и использует статический system device (`X-Site-Id`, `X-Device-Id`, `X-Device-Token`, `X-Client-Version`) для API-вызовов.

## Consequences
- Простая эксплуатация без device registration внутри Django.
- Централизация контроля доступа на стороне SyncServer.
- Требуется безопасное хранение device token в окружении.

## Alternatives Considered
- Регистрация устройств из Warehouse_web (отложено на будущее).
- Анонимные вызовы без device headers (отклонено).
