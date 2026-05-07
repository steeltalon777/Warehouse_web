(function () {
  window.WAREHOUSE_OPERATIONS_CREATE_VERSION = "20260505-draft-pagination";
  window.WAREHOUSE_OPERATIONS_CREATE_DEBUG = {
    initialized: false,
    version: window.WAREHOUSE_OPERATIONS_CREATE_VERSION,
    missingNodes: [],
    itemSearchUrl: "",
    lastSearch: null,
    lastError: null,
  };

  const draftNode = document.getElementById("operation-draft-data");
  const typeOptionsNode = document.getElementById("operation-type-options-data");
  const configNode = document.getElementById("operation-create-config");
  if (!draftNode || !typeOptionsNode || !configNode) {
    window.WAREHOUSE_OPERATIONS_CREATE_DEBUG.missingNodes = [
      !draftNode ? "operation-draft-data" : "",
      !typeOptionsNode ? "operation-type-options-data" : "",
      !configNode ? "operation-create-config" : "",
    ].filter(Boolean);
    console.warn(
      "operations_create.js skipped: required data nodes are missing",
      window.WAREHOUSE_OPERATIONS_CREATE_DEBUG.missingNodes
    );
    return;
  }

  const draftInput = document.getElementById("id_draft_payload");
  const form = document.getElementById("operation-create-form");
  const typeSelect = document.getElementById("operation-type-select");
  const siteSelect = document.getElementById("site-select");
  const sourceSiteSelect = document.getElementById("source-site-select");
  const destinationSiteSelect = document.getElementById("destination-site-select");
  const issuedToNameInput = document.getElementById("issued-to-name-input");
  const effectiveAtInput = document.getElementById("effective-at-input");
  const notesInput = document.getElementById("notes-input");
  const notesLabel = document.getElementById("notes-label");
  const singleSiteRow = document.getElementById("single-site-row");
  const singleSiteLabel = document.getElementById("single-site-label");
  const fixedSiteRow = document.getElementById("fixed-site-row");
  const sourceSiteRow = document.getElementById("source-site-row");
  const destinationSiteRow = document.getElementById("destination-site-row");
  const recipientRow = document.getElementById("recipient-row");
  const quantityHint = document.getElementById("quantity-hint");
  const typeNote = document.getElementById("operation-type-note");
  const itemSearchInput = document.getElementById("item-search-input");
  const itemSearchResultsBody = document.getElementById("item-search-results-body");
  const itemSearchStatus = document.getElementById("item-search-status");
  const selectedItemBox = document.getElementById("selected-item-box");
  const quantityInput = document.getElementById("item-quantity-input");
  const addItemButton = document.getElementById("add-item-button");
  const draftItemsBody = document.getElementById("draft-items-body");
  const draftEmptyRow = document.getElementById("draft-empty-row");
  const draftItemsPagination = document.getElementById("draft-items-pagination");
  const draftItemsPaginationSummary = document.getElementById("draft-items-pagination-summary");
  const draftItemsPaginationInfo = document.getElementById("draft-items-pagination-info");
  const draftItemsPrevPageButton = document.getElementById("draft-items-prev-page");
  const draftItemsNextPageButton = document.getElementById("draft-items-next-page");
  const draftItemsPageSizeSelect = document.getElementById("draft-items-page-size");
  const summaryTypeLabel = document.getElementById("summary-type-label");
  const summaryLineCount = document.getElementById("summary-line-count");
  const summaryQtyTotal = document.getElementById("summary-qty-total");

  const requiredNodes = {
    draftInput,
    form,
    typeSelect,
    siteSelect,
    sourceSiteSelect,
    destinationSiteSelect,
    issuedToNameInput,
    notesInput,
    notesLabel,
    singleSiteRow,
    singleSiteLabel,
    sourceSiteRow,
    destinationSiteRow,
    recipientRow,
    quantityHint,
    typeNote,
    itemSearchInput,
    itemSearchResultsBody,
    itemSearchStatus,
    selectedItemBox,
    quantityInput,
    addItemButton,
    draftItemsBody,
    draftEmptyRow,
    draftItemsPagination,
    draftItemsPaginationSummary,
    draftItemsPaginationInfo,
    draftItemsPrevPageButton,
    draftItemsNextPageButton,
    draftItemsPageSizeSelect,
    summaryTypeLabel,
    summaryLineCount,
    summaryQtyTotal,
  };
  const missingRequiredNodes = Object.entries(requiredNodes)
    .filter(([, node]) => !node)
    .map(([name]) => name);
  if (missingRequiredNodes.length) {
    window.WAREHOUSE_OPERATIONS_CREATE_DEBUG.missingNodes = missingRequiredNodes;
    console.error("operations_create.js skipped: required form nodes are missing", missingRequiredNodes);
    return;
  }

  let state = JSON.parse(draftNode.textContent || "{}");
  const typeOptions = JSON.parse(typeOptionsNode.textContent || "[]");
  const config = JSON.parse(configNode.textContent || "{}");
  window.WAREHOUSE_OPERATIONS_CREATE_DEBUG.itemSearchUrl = config.itemSearchUrl || "";
  const typeMetaByCode = Object.fromEntries(typeOptions.map((item) => [item.code, item]));
  let selectedItem = null;
  let currentSearchResults = [];
  let canAddTemporaryFromSearch = false;
  let temporarySearchQuery = "";
  let searchTimer = null;
  let searchRequestSeq = 0;
  const draftItemsUiState = {
    page: 1,
    pageSize: 20,
  };

  // Получаем default_unit_id из draft-данных
  const defaultUnitId = (draftNode ? JSON.parse(draftNode.textContent || "{}").default_unit_id : null) || "";

  function getCsrfToken() {
    const tokenInput = form ? form.querySelector("input[name=csrfmiddlewaretoken]") : null;
    return tokenInput ? tokenInput.value : "";
  }

  function isValidDateTimeLocal(value) {
    const raw = String(value ?? "").trim();
    return raw === "" || /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(raw);
  }

  function currentDateTimeLocalValue() {
    const now = new Date();
    const offsetMs = now.getTimezoneOffset() * 60000;
    return new Date(now.getTime() - offsetMs).toISOString().slice(0, 16);
  }

  function parseQuantity(value) {
    const raw = String(value ?? "").trim().replace(",", ".");
    const match = raw.match(/^([+-]?)(?:(\d+)(?:\.(\d{0,3}))?|\.(\d{1,3}))$/);
    if (!match) {
      return null;
    }

    const sign = match[1] === "-" ? -1n : 1n;
    const whole = match[2] || "0";
    const fraction = match[3] !== undefined ? match[3] : (match[4] || "");
    const meaningfulWhole = whole.replace(/^0+/, "");
    if (meaningfulWhole.length > 15) {
      return null;
    }

    let milli = BigInt(whole || "0") * 1000n + BigInt((fraction || "").padEnd(3, "0"));
    milli *= sign;

    return {
      milli,
      value: formatQuantityMilli(milli),
    };
  }

  function formatQuantityMilli(milli) {
    const negative = milli < 0n;
    const absolute = negative ? -milli : milli;
    const whole = absolute / 1000n;
    const fraction = absolute % 1000n;
    if (fraction === 0n) {
      return `${negative ? "-" : ""}${whole}`;
    }

    const fractionText = fraction.toString().padStart(3, "0").replace(/0+$/, "");
    return `${negative ? "-" : ""}${whole}.${fractionText}`;
  }

  function isParsedQuantityAllowed(parsedQuantity, allowNegative) {
    return Boolean(
      parsedQuantity
      && parsedQuantity.milli !== 0n
      && (allowNegative || parsedQuantity.milli > 0n)
    );
  }

  function ensureStateDefaults() {
    if (!state || typeof state !== "object") {
      state = {};
    }
    state.operation_type = state.operation_type || "RECEIVE";
    state.site_id = state.site_id ?? "";
    state.source_site_id = state.source_site_id ?? state.site_id ?? "";
    state.destination_site_id = state.destination_site_id ?? "";
    state.issued_to_name = state.issued_to_name || "";
    state.notes = state.notes || "";
    state.effective_at = state.effective_at || (effectiveAtInput ? effectiveAtInput.value : "") || currentDateTimeLocalValue();
    state.items = Array.isArray(state.items) ? state.items : [];

    // Добавляем поле kind к существующим элементам (для обратной совместимости)
    state.items.forEach((item) => {
      if (!item.kind) {
        item.kind = "catalog";
      }
    });

    if (!config.canChooseSourceSite && config.fixedOperatingSiteId) {
      state.site_id = config.fixedOperatingSiteId;
      state.source_site_id = config.fixedOperatingSiteId;
    }
  }

  function currentTypeMeta() {
    return typeMetaByCode[state.operation_type] || typeOptions[0] || null;
  }

  function syncDraftPayload() {
    if (!draftInput) return;
    draftInput.value = JSON.stringify(state);
  }

  function isQuantityValid() {
    const quantity = parseQuantity(quantityInput.value);
    const allowNegative = Boolean((currentTypeMeta() || {}).allow_negative_qty);
    return isParsedQuantityAllowed(quantity, allowNegative);
  }

  function updateAddButtonState() {
    const canAddCatalogItem = Boolean(selectedItem);
    const canAddTemporaryItem = canAddTemporaryFromSearch && Boolean(temporarySearchQuery);
    addItemButton.disabled = !(isQuantityValid() && (canAddCatalogItem || canAddTemporaryItem));
    addItemButton.textContent = canAddTemporaryItem && !canAddCatalogItem
      ? "Добавить временную ТМЦ"
      : "Добавить строку";
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function setSearchStatus(text) {
    itemSearchStatus.textContent = text;
  }

  function parsePositiveInt(value, fallback) {
    const parsed = Number.parseInt(String(value ?? ""), 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
  }

  function ensureDraftItemsPageState(totalItems = (state.items || []).length) {
    draftItemsUiState.pageSize = parsePositiveInt(draftItemsPageSizeSelect.value, 20);
    draftItemsPageSizeSelect.value = String(draftItemsUiState.pageSize);

    const totalPages = Math.max(Math.ceil(totalItems / draftItemsUiState.pageSize), 1);
    draftItemsUiState.page = Math.min(Math.max(draftItemsUiState.page, 1), totalPages);
    return totalPages;
  }

  function showDraftItemsPageForIndex(index) {
    if (!Number.isInteger(index) || index < 0) {
      return;
    }
    draftItemsUiState.page = Math.floor(index / draftItemsUiState.pageSize) + 1;
  }

  function renderDraftItemsPagination(totalItems, totalPages, startIndex, endIndex) {
    const hasRows = totalItems > 0;
    draftItemsPagination.classList.toggle("operation-hidden", !hasRows);

    if (!hasRows) {
      draftItemsPaginationSummary.textContent = "Показано 0 из 0";
      draftItemsPaginationInfo.textContent = "Страница 1 из 1";
      draftItemsPrevPageButton.disabled = true;
      draftItemsNextPageButton.disabled = true;
      return;
    }

    draftItemsPaginationSummary.textContent = `Показаны строки ${startIndex + 1}-${endIndex} из ${totalItems}`;
    draftItemsPaginationInfo.textContent = `Страница ${draftItemsUiState.page} из ${totalPages}`;
    draftItemsPrevPageButton.disabled = draftItemsUiState.page <= 1;
    draftItemsNextPageButton.disabled = draftItemsUiState.page >= totalPages;
  }

  function renderTypeSection() {
    const meta = currentTypeMeta();
    if (!meta) return;

    typeSelect.value = state.operation_type;
    summaryTypeLabel.textContent = meta.label || "Операция";
    typeNote.textContent = meta.description || "";
    notesLabel.textContent = meta.notes_label || "Комментарий";
    notesInput.placeholder = meta.notes_label || "Комментарий";
    quantityHint.textContent = meta.allow_negative_qty
      ? "Для корректировки можно указывать положительное или отрицательное количество с точностью до 3 знаков."
      : "Для большинства операций количество должно быть положительным числом с точностью до 3 знаков.";

    if (state.operation_type === "MOVE") {
      singleSiteRow.classList.add("operation-hidden");
      sourceSiteRow.classList.toggle("operation-hidden", !config.canChooseSourceSite);
      destinationSiteRow.classList.remove("operation-hidden");
    } else {
      singleSiteRow.classList.toggle("operation-hidden", !config.canChooseSourceSite);
      sourceSiteRow.classList.add("operation-hidden");
      destinationSiteRow.classList.add("operation-hidden");
      singleSiteLabel.textContent = meta.single_site_label || "Склад";
    }

    if (fixedSiteRow) {
      fixedSiteRow.classList.toggle("operation-hidden", config.canChooseSourceSite);
    }

    recipientRow.classList.toggle("operation-hidden", !meta.requires_recipient);
    updateAddButtonState();
  }

  function renderSelectedItem() {
    if (!selectedItem) {
      selectedItemBox.classList.add("operation-hidden");
      selectedItemBox.textContent = "";
      updateAddButtonState();
      return;
    }

    selectedItemBox.classList.remove("operation-hidden");
    selectedItemBox.innerHTML = `
      <strong>Выбрано:</strong> ${escapeHtml(selectedItem.name)}
      <span>SKU: ${escapeHtml(selectedItem.sku || "—")}</span>
      <span>Ед. изм.: ${escapeHtml(selectedItem.unit_symbol || "—")}</span>
    `;
    updateAddButtonState();
  }

  function renderItemsTable() {
    const rows = state.items || [];
    draftItemsBody.querySelectorAll("tr[data-draft-row]").forEach((row) => row.remove());

    draftEmptyRow.classList.toggle("operation-hidden", rows.length > 0);
    const totalPages = ensureDraftItemsPageState(rows.length);
    const startIndex = rows.length ? (draftItemsUiState.page - 1) * draftItemsUiState.pageSize : 0;
    const endIndexExclusive = Math.min(startIndex + draftItemsUiState.pageSize, rows.length);
    const visibleRows = rows.slice(startIndex, endIndexExclusive);

    let quantityTotalMilli = 0n;
    rows.forEach((item) => {
      const parsedQuantity = parseQuantity(item.quantity);
      if (parsedQuantity) {
        quantityTotalMilli += parsedQuantity.milli;
      }
    });

    visibleRows.forEach((item) => {
      const row = document.createElement("tr");
      row.dataset.draftRow = "true";

      // Определяем тип строки
      const kind = item.kind || "catalog";
      const isTemporary = kind === "temporary";
      const identifier = isTemporary ? item.client_key : item.item_id;
      const typeBadge = isTemporary ? '<span class="operation-badge operation-badge-warning">Временная</span> ' : '';

      // Для временных ТМЦ единица измерения может быть в unit_symbol или нужно получить из unit_id
      const unitSymbol = item.unit_symbol || "—";
      const sku = item.sku || "—";

      row.innerHTML = `
        <td>${typeBadge}${escapeHtml(item.name)}</td>
        <td>${escapeHtml(sku)}</td>
        <td>${escapeHtml(unitSymbol)}</td>
        <td><input type="number" step="0.001" value="${item.quantity}" data-qty-input="${identifier}" data-item-kind="${kind}"></td>
        <td><button type="button" class="btn btn-secondary btn-small" data-remove-item="${identifier}" data-item-kind="${kind}">Удалить</button></td>
      `;
      draftItemsBody.appendChild(row);
    });

    summaryLineCount.textContent = String(rows.length);
    summaryQtyTotal.textContent = formatQuantityMilli(quantityTotalMilli);
    renderDraftItemsPagination(rows.length, totalPages, startIndex, endIndexExclusive);
    syncDraftPayload();
  }

  function updateStateFromFields() {
    state.operation_type = typeSelect.value;
    state.site_id = config.canChooseSourceSite ? siteSelect.value : config.fixedOperatingSiteId;
    state.source_site_id = config.canChooseSourceSite ? sourceSiteSelect.value : config.fixedOperatingSiteId;
    state.destination_site_id = destinationSiteSelect.value;
    state.issued_to_name = issuedToNameInput.value.trim();
    state.notes = notesInput.value.trim();
    state.effective_at = effectiveAtInput ? effectiveAtInput.value.trim() : "";
    syncDraftPayload();
  }

  function setFieldValuesFromState() {
    typeSelect.value = state.operation_type;
    siteSelect.value = state.site_id || "";
    sourceSiteSelect.value = state.source_site_id || "";
    destinationSiteSelect.value = state.destination_site_id || "";
    issuedToNameInput.value = state.issued_to_name || "";
    notesInput.value = state.notes || "";
    if (effectiveAtInput) {
      effectiveAtInput.value = state.effective_at || "";
    }
  }

  function resetPicker(statusMessage) {
    selectedItem = null;
    currentSearchResults = [];
    canAddTemporaryFromSearch = false;
    temporarySearchQuery = "";
    itemSearchInput.value = "";
    quantityInput.value = "1";
    renderSelectedItem();
    renderSearchResults([], "");
    setSearchStatus(statusMessage || "Введите минимум 2 символа, чтобы увидеть результаты.");
    itemSearchInput.focus();
  }

  function mergeItem(itemData, quantity) {
    const parsedQty = parseQuantity(quantity);
    if (!parsedQty) return null;

    const existingIndex = state.items.findIndex(
      (row) => Number(row.item_id) === Number(itemData.id || itemData.item_id)
    );
    if (existingIndex >= 0) {
      const existing = state.items[existingIndex];
      const existingQty = parseQuantity(existing.quantity);
      const mergedMilli = (existingQty ? existingQty.milli : 0n) + parsedQty.milli;
      if (mergedMilli === 0n) {
        state.items = state.items.filter((row) => Number(row.item_id) !== Number(existing.item_id));
        return { action: "removed", index: Math.max(existingIndex - 1, 0) };
      } else {
        existing.quantity = formatQuantityMilli(mergedMilli);
        return { action: "updated", index: existingIndex };
      }
    }

    state.items.push({
      kind: "catalog",
      item_id: Number(itemData.id || itemData.item_id),
      name: itemData.name,
      sku: itemData.sku || "",
      unit_symbol: itemData.unit_symbol || "",
      quantity: parsedQty.value,
    });
    return { action: "added", index: state.items.length - 1 };
  }

  function addSelectedItem() {
    if (!selectedItem) {
      if (canAddTemporaryFromSearch && temporarySearchQuery) {
        addTemporaryFromSearch(temporarySearchQuery);
        return;
      }
      window.alert("Сначала выберите ТМЦ из результатов поиска или выполните поиск без совпадений.");
      return;
    }

    const quantity = parseQuantity(quantityInput.value);
    const allowNegative = Boolean((currentTypeMeta() || {}).allow_negative_qty);
    if (!quantity) {
      window.alert("Количество должно быть числом с точностью до 3 знаков после запятой.");
      return;
    }
    if (quantity.milli === 0n) {
      window.alert("Количество не может быть нулевым.");
      return;
    }
    if (!allowNegative && quantity.milli < 0n) {
      window.alert("Отрицательное количество доступно только для корректировки.");
      return;
    }

    const mergeResult = mergeItem(selectedItem, quantity.value);
    if (mergeResult) {
      showDraftItemsPageForIndex(mergeResult.index);
    }
    updateStateFromFields();
    renderItemsTable();
    resetPicker();
  }

  function addTemporaryFromSearch(query) {
    const name = String(query || "").trim();
    if (name.length < 2) {
      window.alert("Введите минимум 2 символа для временной ТМЦ.");
      return;
    }

    const quantity = parseQuantity(quantityInput.value);
    const allowNegative = Boolean((currentTypeMeta() || {}).allow_negative_qty);
    if (!quantity) {
      window.alert("Количество должно быть числом с точностью до 3 знаков после запятой.");
      return;
    }
    if (quantity.milli === 0n) {
      window.alert("Количество не может быть нулевым.");
      return;
    }
    if (!allowNegative && quantity.milli < 0n) {
      window.alert("Отрицательное количество доступно только для корректировки.");
      return;
    }

    // Генерируем client_key для временной строки
    const clientKey = "tmp-" + Math.random().toString(36).substring(2, 10);

    state.items.push({
      kind: "temporary",
      client_key: clientKey,
      name: name,
      sku: "",
      unit_id: defaultUnitId || null,
      unit_symbol: "",
      category_id: null,
      quantity: quantity.value,
    });

    showDraftItemsPageForIndex(state.items.length - 1);
    updateStateFromFields();
    renderItemsTable();
    resetPicker(`Временная ТМЦ «${name}» добавлена в строки операции. В базе она создастся только после подтверждения операции.`);
  }

  function buildEmptyResultsRow(message) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="4" class="operation-empty-table">${message}</td>`;
    return row;
  }

  function renderSearchResults(items, query, options = {}) {
    const allowTemporary = options.allowTemporary !== false;
    itemSearchResultsBody.innerHTML = "";
    canAddTemporaryFromSearch = false;
    temporarySearchQuery = "";
    if (!items.length) {
      const trimmedQuery = (query || "").trim();
      if (trimmedQuery.length < 2) {
        itemSearchResultsBody.appendChild(buildEmptyResultsRow("Введите минимум 2 символа, чтобы увидеть результаты."));
      } else if (!allowTemporary) {
        itemSearchResultsBody.appendChild(buildEmptyResultsRow("Не удалось выполнить поиск. Проверьте соединение и попробуйте ещё раз."));
      } else {
        canAddTemporaryFromSearch = true;
        temporarySearchQuery = trimmedQuery;
        // Показываем action-row для добавления временной ТМЦ
        const row = document.createElement("tr");
        row.className = "operation-search-action-row";
        row.dataset.action = "add-temporary";
        row.innerHTML = `
          <td colspan="4">
            <div class="operation-search-action-note">
              Действующая ТМЦ не найдена. Можно добавить временную строку в черновик операции.
            </div>
            <button type="button" class="btn btn-small">
              + Добавить «${escapeHtml(trimmedQuery)}» как временную ТМЦ
            </button>
          </td>
        `;
        row.addEventListener("click", function () {
          addTemporaryFromSearch(trimmedQuery);
        });
        itemSearchResultsBody.appendChild(row);
      }
      updateAddButtonState();
      return;
    }

    items.forEach((item) => {
      const row = document.createElement("tr");
      row.className = "operation-search-result-row";
      if (selectedItem && Number(selectedItem.id) === Number(item.id)) {
        row.classList.add("is-selected");
      }

      row.innerHTML = `
        <td><strong>${escapeHtml(item.name)}</strong></td>
        <td>${escapeHtml(item.sku || "—")}</td>
        <td>${escapeHtml(item.unit_symbol || "—")}</td>
        <td>${escapeHtml(item.category_name || "—")}</td>
      `;

      row.addEventListener("click", function () {
        selectedItem = item;
        renderSelectedItem();
        renderSearchResults(currentSearchResults, itemSearchInput.value);
        quantityInput.focus();
      });

      itemSearchResultsBody.appendChild(row);
    });
    updateAddButtonState();
  }

  function fetchSearchResults(query, options = {}) {
    const addTemporaryWhenEmpty = options.addTemporaryWhenEmpty === true;
    const requestSeq = ++searchRequestSeq;
    window.WAREHOUSE_OPERATIONS_CREATE_DEBUG.lastSearch = {
      query,
      addTemporaryWhenEmpty,
      startedAt: new Date().toISOString(),
    };
    window.WAREHOUSE_OPERATIONS_CREATE_DEBUG.lastError = null;
    setSearchStatus("Ищем совпадения...");
    window.fetch(`${config.itemSearchUrl}?q=${encodeURIComponent(query)}`, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          const error = new Error(payload.error || "Не удалось загрузить результаты поиска.");
          error.status = response.status;
          throw error;
        }
        if (payload && payload.error) {
          throw new Error(payload.error);
        }
        return payload;
      })
      .then((payload) => {
        if (requestSeq !== searchRequestSeq || itemSearchInput.value.trim() !== query) {
          return;
        }
        currentSearchResults = Array.isArray(payload.items) ? payload.items : [];
        window.WAREHOUSE_OPERATIONS_CREATE_DEBUG.lastSearch = {
          ...window.WAREHOUSE_OPERATIONS_CREATE_DEBUG.lastSearch,
          ok: true,
          count: currentSearchResults.length,
          finishedAt: new Date().toISOString(),
        };
        renderSearchResults(currentSearchResults, query);
        setSearchStatus(
          currentSearchResults.length
            ? `Найдено позиций: ${currentSearchResults.length}`
            : "По запросу ничего не найдено."
        );
        if (!currentSearchResults.length && addTemporaryWhenEmpty && temporarySearchQuery) {
          addSelectedItem();
        }
      })
      .catch((error) => {
        if (requestSeq !== searchRequestSeq || itemSearchInput.value.trim() !== query) {
          return;
        }
        window.WAREHOUSE_OPERATIONS_CREATE_DEBUG.lastError = {
          message: error instanceof Error ? error.message : String(error),
          status: error instanceof Error ? error.status : undefined,
          finishedAt: new Date().toISOString(),
        };
        currentSearchResults = [];
        renderSearchResults([], query, { allowTemporary: false });
        if (error instanceof Error && error.message) {
          setSearchStatus(error.message);
          return;
        }
        setSearchStatus("Не удалось загрузить результаты поиска.");
      });
  }

  function triggerAddItemAction() {
    if (!addItemButton.disabled) {
      addItemButton.click();
      return;
    }

    const query = itemSearchInput.value.trim();
    if (query.length < 2) {
      return;
    }
    if (searchTimer) {
      clearTimeout(searchTimer);
    }
    fetchSearchResults(query, { addTemporaryWhenEmpty: true });
  }

  function onSearchInput() {
    const query = itemSearchInput.value.trim();
    selectedItem = null;
    canAddTemporaryFromSearch = false;
    temporarySearchQuery = "";
    renderSelectedItem();
    if (query.length < 2) {
      searchRequestSeq += 1;
      currentSearchResults = [];
      renderSearchResults([], query);
      setSearchStatus("Введите минимум 2 символа, чтобы увидеть результаты.");
      return;
    }

    if (searchTimer) {
      clearTimeout(searchTimer);
    }
    searchTimer = window.setTimeout(function () {
      fetchSearchResults(query);
    }, 220);
  }

  function handleDraftTableClick(event) {
    const removeButton = event.target.closest("[data-remove-item]");
    if (!removeButton) return;
    const identifier = removeButton.dataset.removeItem;
    const kind = removeButton.dataset.itemKind || "catalog";

    if (kind === "catalog") {
      const itemId = Number(identifier);
      state.items = state.items.filter((item) => Number(item.item_id) !== itemId);
    } else {
      // временная ТМЦ
      state.items = state.items.filter((item) => item.client_key !== identifier);
    }
    renderItemsTable();
  }

  function handleDraftTableChange(event) {
    const qtyInput = event.target.closest("[data-qty-input]");
    if (!qtyInput) return;

    const identifier = qtyInput.dataset.qtyInput;
    const kind = qtyInput.dataset.itemKind || "catalog";
    const newQuantity = parseQuantity(qtyInput.value);
    const allowNegative = Boolean((currentTypeMeta() || {}).allow_negative_qty);
    if (!isParsedQuantityAllowed(newQuantity, allowNegative)) {
      renderItemsTable();
      window.alert("Количество должно быть числом с точностью до 3 знаков и соответствовать правилам выбранного типа операции.");
      return;
    }

    state.items = state.items.map((item) => {
      if (kind === "catalog" && Number(item.item_id) === Number(identifier)) {
        return { ...item, quantity: newQuantity.value };
      } else if (kind === "temporary" && item.client_key === identifier) {
        return { ...item, quantity: newQuantity.value };
      }
      return item;
    });
    renderItemsTable();
  }

  function validateBeforeSubmit(event) {
    updateStateFromFields();
    if (!state.items.length) {
      event.preventDefault();
      window.alert("Добавьте хотя бы одну строку ТМЦ.");
      return;
    }

    const meta = currentTypeMeta();
    if (state.operation_type === "MOVE") {
      if (!state.source_site_id || !state.destination_site_id) {
        event.preventDefault();
        window.alert("Для перемещения выберите склад-источник и склад-получатель.");
        return;
      }
      if (String(state.source_site_id) === String(state.destination_site_id)) {
        event.preventDefault();
        window.alert("Склад-источник и склад-получатель должны отличаться.");
        return;
      }
    } else if (!state.site_id) {
      event.preventDefault();
      window.alert("Выберите склад для операции.");
      return;
    }

    if (meta && meta.requires_recipient && !state.issued_to_name) {
      event.preventDefault();
      window.alert("Укажите получателя для выбранного типа операции.");
      return;
    }

    if (!isValidDateTimeLocal(state.effective_at)) {
      event.preventDefault();
      window.alert("Проверьте дату и время операции.");
      return;
    }

    const allowNegative = Boolean((meta || {}).allow_negative_qty);
    const invalidLine = state.items.find((item) => !isParsedQuantityAllowed(parseQuantity(item.quantity), allowNegative));
    if (invalidLine) {
      event.preventDefault();
      window.alert("Проверьте количество в строках операции.");
      return;
    }

    syncDraftPayload();
  }

  ensureStateDefaults();
  ensureDraftItemsPageState();
  setFieldValuesFromState();
  renderTypeSection();
  renderSelectedItem();
  renderItemsTable();
  renderSearchResults([], "");
  setSearchStatus("Введите минимум 2 символа, чтобы увидеть результаты.");
  updateAddButtonState();

  typeSelect.addEventListener("change", function () {
    updateStateFromFields();
    renderTypeSection();
    renderItemsTable();
  });
  siteSelect.addEventListener("change", updateStateFromFields);
  sourceSiteSelect.addEventListener("change", updateStateFromFields);
  destinationSiteSelect.addEventListener("change", updateStateFromFields);
  issuedToNameInput.addEventListener("input", updateStateFromFields);
  notesInput.addEventListener("input", updateStateFromFields);
  if (effectiveAtInput) effectiveAtInput.addEventListener("change", updateStateFromFields);
  itemSearchInput.addEventListener("input", onSearchInput);
  quantityInput.addEventListener("input", updateAddButtonState);
  addItemButton.addEventListener("click", addSelectedItem);
  draftItemsBody.addEventListener("click", handleDraftTableClick);
  draftItemsBody.addEventListener("change", handleDraftTableChange);
  draftItemsPrevPageButton.addEventListener("click", function () {
    draftItemsUiState.page = Math.max(draftItemsUiState.page - 1, 1);
    renderItemsTable();
  });
  draftItemsNextPageButton.addEventListener("click", function () {
    draftItemsUiState.page += 1;
    renderItemsTable();
  });
  draftItemsPageSizeSelect.addEventListener("change", function () {
    const currentFirstVisibleIndex = Math.max((draftItemsUiState.page - 1) * draftItemsUiState.pageSize, 0);
    draftItemsUiState.pageSize = parsePositiveInt(draftItemsPageSizeSelect.value, 20);
    draftItemsUiState.page = Math.floor(currentFirstVisibleIndex / draftItemsUiState.pageSize) + 1;
    renderItemsTable();
  });
  quantityInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      triggerAddItemAction();
    }
  });
  itemSearchInput.addEventListener("keydown", function (event) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    triggerAddItemAction();
  });
  form.addEventListener("submit", validateBeforeSubmit);
  window.WAREHOUSE_OPERATIONS_CREATE_DEBUG.initialized = true;
  console.info("operations_create.js initialized", window.WAREHOUSE_OPERATIONS_CREATE_DEBUG);
})();
