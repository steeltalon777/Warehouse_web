(function () {
  const draftNode = document.getElementById("operation-draft-data");
  const typeOptionsNode = document.getElementById("operation-type-options-data");
  const configNode = document.getElementById("operation-create-config");
  if (!draftNode || !typeOptionsNode || !configNode) return;

  const draftInput = document.getElementById("id_draft_payload");
  const form = document.getElementById("operation-create-form");
  const typeSelect = document.getElementById("operation-type-select");
  const siteSelect = document.getElementById("site-select");
  const sourceSiteSelect = document.getElementById("source-site-select");
  const destinationSiteSelect = document.getElementById("destination-site-select");
  const issuedToNameInput = document.getElementById("issued-to-name-input");
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
  const summaryTypeLabel = document.getElementById("summary-type-label");
  const summaryLineCount = document.getElementById("summary-line-count");
  const summaryQtyTotal = document.getElementById("summary-qty-total");

  let state = JSON.parse(draftNode.textContent || "{}");
  const typeOptions = JSON.parse(typeOptionsNode.textContent || "[]");
  const config = JSON.parse(configNode.textContent || "{}");
  const typeMetaByCode = Object.fromEntries(typeOptions.map((item) => [item.code, item]));
  let selectedItem = null;
  let currentSearchResults = [];
  let searchTimer = null;

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
    state.items = Array.isArray(state.items) ? state.items : [];

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
    addItemButton.disabled = !(selectedItem && isQuantityValid());
  }

  function setSearchStatus(text) {
    itemSearchStatus.textContent = text;
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
      <strong>Выбрано:</strong> ${selectedItem.name}
      <span>SKU: ${selectedItem.sku || "—"}</span>
      <span>Ед. изм.: ${selectedItem.unit_symbol || "—"}</span>
    `;
    updateAddButtonState();
  }

  function renderItemsTable() {
    const rows = state.items || [];
    draftItemsBody.querySelectorAll("tr[data-draft-row]").forEach((row) => row.remove());

    draftEmptyRow.classList.toggle("operation-hidden", rows.length > 0);

    let quantityTotalMilli = 0n;
    rows.forEach((item) => {
      const parsedQuantity = parseQuantity(item.quantity);
      if (parsedQuantity) {
        quantityTotalMilli += parsedQuantity.milli;
      }
      const row = document.createElement("tr");
      row.dataset.draftRow = "true";
      row.innerHTML = `
        <td>${item.name}</td>
        <td>${item.sku || "—"}</td>
        <td>${item.unit_symbol || "—"}</td>
        <td><input type="number" step="0.001" value="${item.quantity}" data-qty-input="${item.item_id}"></td>
        <td><button type="button" class="btn btn-secondary btn-small" data-remove-item="${item.item_id}">Удалить</button></td>
      `;
      draftItemsBody.appendChild(row);
    });

    summaryLineCount.textContent = String(rows.length);
    summaryQtyTotal.textContent = formatQuantityMilli(quantityTotalMilli);
    syncDraftPayload();
  }

  function updateStateFromFields() {
    state.operation_type = typeSelect.value;
    state.site_id = config.canChooseSourceSite ? siteSelect.value : config.fixedOperatingSiteId;
    state.source_site_id = config.canChooseSourceSite ? sourceSiteSelect.value : config.fixedOperatingSiteId;
    state.destination_site_id = destinationSiteSelect.value;
    state.issued_to_name = issuedToNameInput.value.trim();
    state.notes = notesInput.value.trim();
    syncDraftPayload();
  }

  function setFieldValuesFromState() {
    typeSelect.value = state.operation_type;
    siteSelect.value = state.site_id || "";
    sourceSiteSelect.value = state.source_site_id || "";
    destinationSiteSelect.value = state.destination_site_id || "";
    issuedToNameInput.value = state.issued_to_name || "";
    notesInput.value = state.notes || "";
  }

  function resetPicker() {
    selectedItem = null;
    currentSearchResults = [];
    itemSearchInput.value = "";
    quantityInput.value = "1";
    renderSelectedItem();
    renderSearchResults([]);
    setSearchStatus("Введите минимум 2 символа, чтобы увидеть результаты.");
    itemSearchInput.focus();
  }

  function mergeItem(itemData, quantity) {
    const parsedQty = parseQuantity(quantity);
    if (!parsedQty) return;

    const existing = state.items.find((row) => Number(row.item_id) === Number(itemData.id || itemData.item_id));
    if (existing) {
      const existingQty = parseQuantity(existing.quantity);
      const mergedMilli = (existingQty ? existingQty.milli : 0n) + parsedQty.milli;
      if (mergedMilli === 0n) {
        state.items = state.items.filter((row) => Number(row.item_id) !== Number(existing.item_id));
      } else {
        existing.quantity = formatQuantityMilli(mergedMilli);
      }
      return;
    }

    state.items.push({
      item_id: Number(itemData.id || itemData.item_id),
      name: itemData.name,
      sku: itemData.sku || "",
      unit_symbol: itemData.unit_symbol || "",
      quantity: parsedQty.value,
    });
  }

  function addSelectedItem() {
    if (!selectedItem) {
      window.alert("Сначала выберите ТМЦ из результатов поиска.");
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

    mergeItem(selectedItem, quantity.value);
    updateStateFromFields();
    renderItemsTable();
    resetPicker();
  }

  function buildEmptyResultsRow(message) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="4" class="operation-empty-table">${message}</td>`;
    return row;
  }

  function renderSearchResults(items) {
    itemSearchResultsBody.innerHTML = "";
    if (!items.length) {
      const emptyMessage = itemSearchInput.value.trim().length < 2
        ? "Введите минимум 2 символа, чтобы увидеть результаты."
        : "По запросу ничего не найдено.";
      itemSearchResultsBody.appendChild(buildEmptyResultsRow(emptyMessage));
      return;
    }

    items.forEach((item) => {
      const row = document.createElement("tr");
      row.className = "operation-search-result-row";
      if (selectedItem && Number(selectedItem.id) === Number(item.id)) {
        row.classList.add("is-selected");
      }

      row.innerHTML = `
        <td><strong>${item.name}</strong></td>
        <td>${item.sku || "—"}</td>
        <td>${item.unit_symbol || "—"}</td>
        <td>${item.category_name || "—"}</td>
      `;

      row.addEventListener("click", function () {
        selectedItem = item;
        renderSelectedItem();
        renderSearchResults(currentSearchResults);
        quantityInput.focus();
      });

      itemSearchResultsBody.appendChild(row);
    });
  }

  function fetchSearchResults(query) {
    setSearchStatus("Ищем совпадения...");
    window.fetch(`${config.itemSearchUrl}?q=${encodeURIComponent(query)}`, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || "Не удалось загрузить результаты поиска.");
        }
        if (payload && payload.error) {
          throw new Error(payload.error);
        }
        return payload;
      })
      .then((payload) => {
        currentSearchResults = Array.isArray(payload.items) ? payload.items : [];
        renderSearchResults(currentSearchResults);
        setSearchStatus(
          currentSearchResults.length
            ? `Найдено позиций: ${currentSearchResults.length}`
            : "По запросу ничего не найдено."
        );
      })
      .catch((error) => {
        currentSearchResults = [];
        renderSearchResults([]);
        if (error instanceof Error && error.message) {
          setSearchStatus(error.message);
          return;
        }
        setSearchStatus("Не удалось загрузить результаты поиска.");
      });
  }

  function onSearchInput() {
    const query = itemSearchInput.value.trim();
    selectedItem = null;
    renderSelectedItem();
    if (query.length < 2) {
      currentSearchResults = [];
      renderSearchResults([]);
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
    const itemId = Number(removeButton.dataset.removeItem);
    state.items = state.items.filter((item) => Number(item.item_id) !== itemId);
    renderItemsTable();
  }

  function handleDraftTableChange(event) {
    const qtyInput = event.target.closest("[data-qty-input]");
    if (!qtyInput) return;

    const itemId = Number(qtyInput.dataset.qtyInput);
    const newQuantity = parseQuantity(qtyInput.value);
    const allowNegative = Boolean((currentTypeMeta() || {}).allow_negative_qty);
    if (!isParsedQuantityAllowed(newQuantity, allowNegative)) {
      renderItemsTable();
      window.alert("Количество должно быть числом с точностью до 3 знаков и соответствовать правилам выбранного типа операции.");
      return;
    }

    state.items = state.items.map((item) => (
      Number(item.item_id) === itemId ? { ...item, quantity: newQuantity.value } : item
    ));
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
  setFieldValuesFromState();
  renderTypeSection();
  renderSelectedItem();
  renderItemsTable();
  renderSearchResults([]);
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
  itemSearchInput.addEventListener("input", onSearchInput);
  quantityInput.addEventListener("input", updateAddButtonState);
  addItemButton.addEventListener("click", addSelectedItem);
  draftItemsBody.addEventListener("click", handleDraftTableClick);
  draftItemsBody.addEventListener("change", handleDraftTableChange);
  quantityInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      addSelectedItem();
    }
  });
  form.addEventListener("submit", validateBeforeSubmit);
})();
