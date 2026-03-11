# ADR-0001: Django modular monolith as application architecture

## Status
Accepted

## Context
Проект реализует веб-интерфейс склада с несколькими доменными зонами (catalog, users, client, documents). Требуется быстрый запуск, единая кодовая база и стандартные механизмы аутентификации/админки.

## Decision
Использовать модульный монолит на Django с разделением по `apps/*` и общей конфигурацией в `config/*`.

## Consequences
Плюсы:
- Быстрый старт и единый deployment-юнит.
- Простая навигация по доменам через Django apps.
- Использование стандартных возможностей Django (admin, auth, generic views).

Минусы:
- Риск роста связности между app-модулями.
- Нужна дисциплина по границам слоев, чтобы избежать «fat views».

## Alternatives Considered
### Option 1: Микросервисы
Сложнее операционно для текущего масштаба проекта.

### Option 2: Single-app Django project
Упрощает структуру на старте, но ухудшает масштабируемость кода по доменам.
