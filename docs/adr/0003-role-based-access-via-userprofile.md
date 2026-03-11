# ADR-0003: Role-based access control via UserProfile extension

## Status
Accepted

## Context
Системе нужен ролевой контроль (`root`, `chief_storekeeper`, `storekeeper`) и привязка пользователя к площадке/складу.

## Decision
Расширить стандартного Django User через `UserProfile` (OneToOne) и хранить роль/сайт в профиле. Проверки доступа централизовать в `apps/common/permissions.py`.

## Consequences
Плюсы:
- Не требуется кастомная модель User на раннем этапе.
- Единая точка ролевых проверок.
- Гибкость для добавления доменных атрибутов профиля.

Минусы:
- Нужно контролировать наличие profile у каждого пользователя.
- Дополнительный join при чтении роли.

## Alternatives Considered
### Option 1: Полностью кастомный AUTH_USER_MODEL
Более гибко, но выше стоимость внедрения и миграций.

### Option 2: Django Groups/Permissions only
Не покрывает доменные атрибуты (site) так явно без дополнительных связей.
