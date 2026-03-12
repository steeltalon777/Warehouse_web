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
