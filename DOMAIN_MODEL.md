# DOMAIN_MODEL

## Entity: Category (`apps/catalog/models.py`)
Описание: категория каталога с древовидной иерархией.

Fields:
- `id` (UUID, PK)
- `name`
- `code`
- `parent` (FK to `Category`, nullable)
- `is_active`
- `sort_order`
- `created_at`, `updated_at`

Relations:
- parent category (`parent`)
- child categories (`children`)
- items (`items`)

## Entity: Unit (`apps/catalog/models.py`)
Описание: единица измерения.

Fields:
- `id` (UUID, PK)
- `code` (unique)
- `name`
- `created_at`

Relations:
- items (`items`)

## Entity: Item (`apps/catalog/models.py`)
Описание: номенклатурная позиция (товар/ТМЦ).

Fields:
- `id` (UUID, PK)
- `name`
- `sku`
- `category` (FK to `Category`, nullable)
- `unit` (FK to `Unit`, protected)
- `is_active`
- `created_at`, `updated_at`

Relations:
- category (`category`)
- unit (`unit`)

## Entity: Site (`apps/users/models.py`)
Описание: площадка/объект, к которому привязываются пользователи.

Fields:
- `name` (unique)
- `code` (unique)
- `is_active`
- `created_at`

Relations:
- users (`users`)

## Entity: UserProfile (`apps/users/models.py`)
Описание: расширение стандартного Django User с ролью и site.

Fields:
- `user` (OneToOne to Django User)
- `role` (`root`, `chief_storekeeper`, `storekeeper`)
- `site` (FK to `Site`, nullable)
- `is_active`
- `created_at`, `updated_at`

Relations:
- user profile for auth user (`profile`)
- site membership (`site`)
