# MEMORY

## System architecture
Проект реализован как Django web-клиент для складской предметной области. Используется модульная структура по приложениям и серверный рендер UI.

## Core entities
- `Category`: иерархия категорий, защита от циклов.
- `Unit`: единицы измерения с уникальным кодом.
- `Item`: номенклатура, связанная с категорией и единицей.
- `Site`: площадка/склад.
- `UserProfile`: роль и привязка пользователя к площадке.

## Data model decisions
- UUID как PK для сущностей каталога.
- Self-reference для дерева категорий.
- `UserProfile` как расширение стандартного Django User через OneToOne.
- Создание профиля пользователя через signals при создании User.

## API design
- HTML-first: проект отдает шаблонные страницы.
- Роутинг разделен по app-уровню.
- Доступ к маршрутам защищается сочетанием `LoginRequiredMixin/@login_required` и role checks.

## Business rules
- Управление каталогом доступно ролям `root` и `chief_storekeeper`.
- Client dashboard доступен только активным профилям или superuser.
- Новые пользователи получают роль `storekeeper` по умолчанию.

## Known pitfalls
- Часть бизнес-логики находится в view-слое; service layer не везде выделен явно.
- Есть дублирование SyncServer клиента в двух пакетах (`common/services` и `integration`).
- Модуль `documents` пока не реализован функционально.

## Future architecture
- Выделить единый integration gateway к SyncServer.
- Укрепить service layer для сложных бизнес-сценариев.
- Развить модуль документов и операции склада.
- Подготовить переход на production-friendly БД (например, PostgreSQL).
