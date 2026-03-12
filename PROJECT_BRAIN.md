# PROJECT_BRAIN

## Strategic direction
1. Django остаётся web/admin client.
2. SyncServer владеет domain truth.
3. Legacy Django domain models — transitional compatibility only.

## Implemented direction
- Root/admin panel для users/roles/sites через SyncServer API.
- Chief/storekeeper UI разделены по сценариям, но используют общий API-first integration layer.
- UI переведён на production-friendly static + unified layout.

## Next steps
- Расширять фильтры и bulk-операции без переноса бизнес-логики в Django ORM.
- Выравнивать WPF/mobile/offline клиенты на те же SyncServer domain users/roles/sites.
