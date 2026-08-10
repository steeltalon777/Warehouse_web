# DEPLOYMENT

## Production assumptions
- `DJANGO_ENV=production`
- Django service DB обязательно PostgreSQL (не sqlite).
- SyncServer URL внутри docker-сети: `http://syncserver:8000`.

## Required DB env for Django service DB
- `DB_ENGINE=django.db.backends.postgresql`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`
- `DB_CONN_MAX_AGE`

## Static strategy
- WhiteNoise middleware включён в `config/settings/production.py`.
- `collectstatic` обязателен перед запуском production контейнера.
- `STORAGES['staticfiles'] = whitenoise.storage.CompressedManifestStaticFilesStorage`.

## Network / nginx notes
- nginx должен проксировать Django и SyncServer в единой backend network.
- Заголовки клиента (`X-Site-Id`, `X-Device-Id`, `X-Device-Token`, `X-Client-Version`) должны доходить до SyncServer.
- Разделение БД Django/SyncServer должно сохраняться во всех окружениях.

## Periodic catalog cache reconciliation

Кэш каталога (`catalog_cache_item`) периодически сверяется с SyncServer,
чтобы деактивированные/удалённые позиции не оставались ghost-записями
в fast-поиске.

- Рекомендуемый интервал — ежечасно (cron или systemd-timer).
- Команда:
  - `docker compose exec warehouse_web python manage.py sync_catalog_cache`, или
  - `make sync-catalog-cache` (тот же вызов из корня workspace).
- Пример cron-записи:
  ```
  0 * * * * cd /home/makc/AI_sandbox/warehouse_solution && make sync-catalog-cache >> /var/log/sync-catalog-cache.log 2>&1
  ```

Поведение прунинга:
- Сверка выполняется постраничным полным сканом (`sync_items()`).
- Прунинг кэша (массовая деактивация невидимых записей) происходит ТОЛЬКО
  после полного успешного скана, когда число обработанных записей совпадает
  с удалённым `total_count`.
- При abort/partial-скане кэш НЕ прунится: в `CatalogCacheSyncStats` фиксируется
  `aborted_reason` (например `browse_failed`, `count_mismatch`, `max_pages_reached`),
  а диагностику можно смотреть в логах/статистике запуска.
- Инкрементальная деактивация отдельных неактивных позиций также выполняется
  best-effort в BFF resolve-view без изменения ответа клиенту.
