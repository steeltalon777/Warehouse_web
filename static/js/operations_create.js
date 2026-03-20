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
  const itemSearchResults = document.getElementById("item-search-results");
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
  let searchTimer = null;

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

  function renderTypeSection() {
    const meta = currentTypeMeta();
    if (!meta) return;

    typeSelect.value = state.operation_type;
    summaryTypeLabel.textContent = meta.label || "Операция";
    typeNote.textContent = meta.description || "";
    notesLabel.textContent = meta.notes_label || "Комментарий";
    notesInput.placeholder = meta.notes_label || "Комментарий";
    quantityHint.textContent = meta.allow_negative_qty
      ? "Для корректировки можно указывать как положительное, так и отрицательное количество."
      : "Для большинства операций количество должно быть положительным целым числом.";

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
  }

  function renderSelectedItem() {
    if (!selectedItem) {
      selectedItemBox.classList.add("operation-hidden");
      selectedItemBox.textContent = "";
      return;
    }
    selectedItemBox.classList.remove("operation-hidden");
    selectedItemBox.innerHTML = `
      <strong>${selectedItem.name}</strong>
      <span>SKU: ${selectedItem.sku || "—"}</span>
      <span>Ед. изм.: ${selectedItem.unit_symbol || "—"}</span>
    `;
  }

  function renderItemsTable() {
    const rows = state.items || [];
    draftItemsBody.querySelectorAll("tr[data-draft-row]").forEach((row) => row.remove());

    draftEmptyRow.classList.toggle("operation-hidden", rows.length > 0);

    let quantityTotal = 0;
    rows.forEach((item) => {
      quantityTotal += Number(item.quantity || 0);
      const row = document.createElement("tr");
      row.dataset.draftRow = "true";
      row.innerHTML = `
        <td>${item.name}</td>
        <td>${item.sku || "—"}</td>
        <td>${item.unit_symbol || "—"}</td>
        <td><input type="number" step="1" value="${item.quantity}" data-qty-input="${item.item_id}"></td>
        <td><button type="button" class="btn btn-secondary btn-small" data-remove-item="${item.item_id}">Удалить</button></td>
      `;
      draftItemsBody.appendChild(row);
    });

    summaryLineCount.textContent = String(rows.length);
    summaryQtyTotal.textContent = String(quantityTotal);
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
    itemSearchInput.value = "";
    quantityInput.value = "1";
    renderSelectedItem();
    renderSearchResults([]);
    itemSearchInput.focus();
  }

  function mergeItem(itemData, quantity) {
    const normalizedQty = Number(quantity);
    const existing = state.items.find((row) => Number(row.item_id) === Number(itemData.id || itemData.item_id));
    if (existing) {
      existing.quantity = Number(existing.quantity) + normalizedQty;
      if (existing.quantity === 0) {
        state.items = state.items.filter((row) => Number(row.item_id) !== Number(existing.item_id));
      }
      return;
    }

    state.items.push({
      item_id: Number(itemData.id || itemData.item_id),
      name: itemData.name,
      sku: itemData.sku || "",
      unit_symbol: itemData.unit_symbol || "",
      quantity: normalizedQty,
    });
  }

  function addSelectedItem() {
    if (!selectedItem) {
      window.alert("Сначала выберите ТМЦ из результатов поиска.");
      return;
    }

    const quantity = Number(quantityInput.value);
    const allowNegative = Boolean((currentTypeMeta() || {}).allow_negative_qty);
    if (!Number.isInteger(quantity) || quantity === 0) {
      window.alert("Количество должно быть целым числом и не может быть нулевым.");
      return;
    }
    if (!allowNegative && quantity < 0) {
      window.alert("Отрицательное количество доступно только для корректировки.");
      return;
    }

    mergeItem(selectedItem, quantity);
    updateStateFromFields();
    renderItemsTable();
    resetPicker();
  }

  function renderSearchResults(items) {
    itemSearchResults.innerHTML = "";
    if (!items.length) {
      itemSearchResults.classList.add("operation-hidden");
      return;
    }

    items.forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "operation-combobox-item";
      button.innerHTML = `
        <strong>${item.name}</strong>
        <span>SKU: ${item.sku || "—"}</span>
        <span>Ед. изм.: ${item.unit_symbol || "—"}</span>
      `;
      button.addEventListener("click", function () {
        selectedItem = item;
        renderSelectedItem();
        renderSearchResults([]);
        quantityInput.focus();
      });
      itemSearchResults.appendChild(button);
    });

    itemSearchResults.classList.remove("operation-hidden");
  }

  function fetchSearchResults(query) {
    window.fetch(`${config.itemSearchUrl}?q=${encodeURIComponent(query)}`, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((response) => response.json())
      .then((payload) => {
        renderSearchResults(Array.isArray(payload.items) ? payload.items : []);
      })
      .catch(() => {
        renderSearchResults([]);
      });
  }

  function onSearchInput() {
    const query = itemSearchInput.value.trim();
    if (query.length < 2) {
      renderSearchResults([]);
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
    const newQuantity = Number(qtyInput.value);
    const allowNegative = Boolean((currentTypeMeta() || {}).allow_negative_qty);
    if (!Number.isInteger(newQuantity) || newQuantity === 0 || (!allowNegative && newQuantity < 0)) {
      renderItemsTable();
      window.alert("Количество должно соответствовать правилам выбранного типа операции.");
      return;
    }

    state.items = state.items.map((item) => (
      Number(item.item_id) === itemId ? { ...item, quantity: newQuantity } : item
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

    syncDraftPayload();
  }

  ensureStateDefaults();
  setFieldValuesFromState();
  renderTypeSection();
  renderSelectedItem();
  renderItemsTable();

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
  document.addEventListener("click", function (event) {
    if (!event.target.closest("#item-combobox")) {
      renderSearchResults([]);
    }
  });
})();
