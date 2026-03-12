# AI_ENTRY_POINTS

## Кодовые входы
1. `apps/integration/syncserver_client.py`
   - endpoints: users, roles, sites, catalog, balances, operations.
2. `apps/client/services.py`
   - orchestration сервисы для root/storekeeper экранов.
3. `apps/client/views.py`
   - root control panel + storekeeper workflows.
4. `apps/catalog/services.py`, `apps/catalog/views.py`
   - chief workflows через SyncServer API.
5. `config/settings/production.py`
   - production DB/static policy.
