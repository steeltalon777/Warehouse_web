(function () {
  function initTreeToggles() {
    document.querySelectorAll("[data-tree-toggle]").forEach(function (button) {
      if (button.dataset.treeBound === "true") return;
      button.dataset.treeBound = "true";
      button.addEventListener("click", function () {
        var targetId = button.getAttribute("data-tree-toggle");
        if (!targetId) return;
        var target = document.getElementById(targetId);
        if (!target) return;
        var expanded = button.getAttribute("aria-expanded") === "true";
        button.setAttribute("aria-expanded", expanded ? "false" : "true");
        button.classList.toggle("is-open", !expanded);
        target.hidden = expanded;
      });
    });
  }

  function initSearchableSelects() {
    document.querySelectorAll("select[data-searchable-select]").forEach(function (select) {
      if (select.dataset.enhanced === "true") return;
      select.dataset.enhanced = "true";

      var wrapper = document.createElement("div");
      wrapper.className = "search-select";

      var input = document.createElement("input");
      input.type = "text";
      input.className = "search-select-input";
      input.autocomplete = "off";
      input.placeholder = select.dataset.placeholder || "Начните вводить...";

      var clearButton = document.createElement("button");
      clearButton.type = "button";
      clearButton.className = "search-select-clear";
      clearButton.textContent = "Сброс";

      var panel = document.createElement("div");
      panel.className = "search-select-panel";
      panel.hidden = true;

      var list = document.createElement("div");
      list.className = "search-select-list";
      panel.appendChild(list);

      select.parentNode.insertBefore(wrapper, select.nextSibling);
      wrapper.appendChild(input);
      wrapper.appendChild(clearButton);
      wrapper.appendChild(panel);
      select.classList.add("search-select-native");

      if (select.id) {
        input.id = select.id + "__combobox";
        var label = document.querySelector('label[for="' + select.id + '"]');
        if (label) label.setAttribute("for", input.id);
      }

      var state = {
        items: [],
        activeIndex: -1,
        hasBlankOption: false
      };

      function readItems() {
        state.items = Array.from(select.options).map(function (option) {
          return {
            value: option.value,
            label: option.textContent || "",
            normalized: (option.textContent || "").toLowerCase(),
            disabled: option.disabled
          };
        });
        state.hasBlankOption = state.items.some(function (item) {
          return item.value === "";
        });
      }

      function syncInputFromSelect() {
        var option = select.options[select.selectedIndex];
        input.value = option && option.value ? option.textContent : "";
        clearButton.hidden = !state.hasBlankOption || !option || !option.value;
      }

      function closePanel() {
        panel.hidden = true;
        wrapper.classList.remove("is-open");
        state.activeIndex = -1;
      }

      function openPanel() {
        panel.hidden = false;
        wrapper.classList.add("is-open");
        renderList(input.value);
      }

      function pick(value) {
        select.value = value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        syncInputFromSelect();
        closePanel();
      }

      function renderList(query) {
        list.innerHTML = "";
        var normalizedQuery = (query || "").trim().toLowerCase();
        var filtered = state.items.filter(function (item) {
          if (item.disabled) return false;
          if (!normalizedQuery) return true;
          return item.normalized.indexOf(normalizedQuery) !== -1;
        });

        if (!filtered.length) {
          var empty = document.createElement("div");
          empty.className = "search-select-empty";
          empty.textContent = "Ничего не найдено";
          list.appendChild(empty);
          state.activeIndex = -1;
          return;
        }

        filtered.forEach(function (item, index) {
          var optionButton = document.createElement("button");
          optionButton.type = "button";
          optionButton.className = "search-select-option";
          optionButton.textContent = item.label;
          if (item.value === select.value) {
            optionButton.classList.add("is-selected");
          }
          if (index === state.activeIndex) {
            optionButton.classList.add("is-active");
          }
          optionButton.addEventListener("mousedown", function (event) {
            event.preventDefault();
            pick(item.value);
          });
          list.appendChild(optionButton);
        });
      }

      function moveActive(step) {
        var options = Array.from(list.querySelectorAll(".search-select-option"));
        if (!options.length) return;
        state.activeIndex += step;
        if (state.activeIndex < 0) state.activeIndex = options.length - 1;
        if (state.activeIndex >= options.length) state.activeIndex = 0;
        options.forEach(function (option, index) {
          option.classList.toggle("is-active", index === state.activeIndex);
        });
      }

      readItems();
      syncInputFromSelect();

      input.addEventListener("focus", openPanel);
      input.addEventListener("click", openPanel);
      input.addEventListener("input", function () {
        state.activeIndex = -1;
        openPanel();
      });
      input.addEventListener("keydown", function (event) {
        if (panel.hidden && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
          openPanel();
          event.preventDefault();
          return;
        }
        if (event.key === "ArrowDown") {
          event.preventDefault();
          moveActive(1);
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          moveActive(-1);
        } else if (event.key === "Enter") {
          var active = list.querySelector(".search-select-option.is-active");
          if (active) {
            event.preventDefault();
            active.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
          }
        } else if (event.key === "Escape") {
          closePanel();
        }
      });

      clearButton.addEventListener("click", function () {
        if (!state.hasBlankOption) return;
        pick("");
        input.focus();
      });

      select.addEventListener("change", function () {
        readItems();
        syncInputFromSelect();
      });

      document.addEventListener("click", function (event) {
        if (!wrapper.contains(event.target)) {
          closePanel();
        }
      });
    });
  }

  function initTagInputs() {
    document.querySelectorAll("input[data-tag-input]").forEach(function (input) {
      if (input.dataset.tagBound === "true") return;
      input.dataset.tagBound = "true";

      var wrapper = document.createElement("div");
      wrapper.className = "tag-input";

      var chipsContainer = document.createElement("div");
      chipsContainer.className = "tag-input__chips";

      var field = document.createElement("input");
      field.type = "text";
      field.className = "tag-input__field";
      field.placeholder = input.placeholder || "";
      field.autocomplete = "off";

      wrapper.appendChild(chipsContainer);
      wrapper.appendChild(field);
      input.parentNode.insertBefore(wrapper, input.nextSibling);
      input.type = "hidden";

      function setValue(tags) {
        input.value = tags.join(", ");
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }

      function renderChips() {
        chipsContainer.innerHTML = "";
        var tags = input.value ? input.value.split(",").map(function (t) { return t.trim(); }).filter(Boolean) : [];
        tags.forEach(function (tag) {
          var chip = document.createElement("span");
          chip.className = "tag-input__chip";
          chip.textContent = tag;

          var removeBtn = document.createElement("button");
          removeBtn.type = "button";
          removeBtn.className = "tag-input__remove";
          removeBtn.textContent = "\u00d7";
          removeBtn.addEventListener("click", function () {
            var remaining = tags.filter(function (t) { return t !== tag; });
            setValue(remaining);
            renderChips();
            field.focus();
          });

          chip.appendChild(removeBtn);
          chipsContainer.appendChild(chip);
        });
      }

      function addTag(raw) {
        var tag = raw.trim().toLowerCase().replace(/^#+/, "");
        if (!tag) return;
        var existing = (input.value || "").split(",").map(function (t) { return t.trim().toLowerCase(); });
        if (existing.indexOf(tag) !== -1) return;
        var newVal = input.value ? input.value + ", " + tag : tag;
        setValue(newVal.split(",").map(function (t) { return t.trim(); }).filter(Boolean).join(", "));
        renderChips();
      }

      field.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === ",") {
          event.preventDefault();
          var raw = field.value;
          if (raw.trim()) {
            addTag(raw);
            field.value = "";
          }
        }
        if (event.key === "Backspace" && !field.value) {
          var tags = input.value ? input.value.split(",").map(function (t) { return t.trim(); }).filter(Boolean) : [];
          if (tags.length) {
            tags.pop();
            setValue(tags);
            renderChips();
          }
        }
      });

      field.addEventListener("blur", function () {
        var raw = field.value;
        if (raw.trim()) {
          addTag(raw);
          field.value = "";
        }
      });

      renderChips();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTreeToggles();
    initSearchableSelects();
    initTagInputs();
  });
})();
