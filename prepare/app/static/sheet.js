// Inventory spreadsheet: track edited cells, send only those, tick rows for bulk changes,
// filter and sort in the page. Without this script the page still works: every cell
// is sent and the server keeps only what changed.
(function () {
  var sheet = document.getElementById("sheet"), bulk = document.getElementById("bulk");
  if (!sheet) return;
  var rows = Array.prototype.slice.call(sheet.querySelectorAll("tbody tr[data-id]"));
  var cells = sheet.querySelectorAll("tbody input, tbody select");
  var dirtyCount = document.getElementById("dirty-count");

  function orig(el) { return el.dataset.orig; }
  cells.forEach(function (el) { el.dataset.orig = el.value; });

  function refreshDirty() {
    var changedRows = 0;
    rows.forEach(function (tr) {
      var any = false;
      tr.querySelectorAll("input:not([form]), select").forEach(function (el) {
        var d = el.value !== orig(el);
        el.classList.toggle("changed", d);
        any = any || d;
      });
      tr.classList.toggle("dirty", any);
      if (any) changedRows++;
    });
    dirtyCount.textContent = changedRows ? changedRows + " row" + (changedRows === 1 ? "" : "s") + " changed" : "No changes";
    document.body.classList.toggle("has-changes", changedRows > 0);
    return changedRows;
  }

  sheet.addEventListener("input", refreshDirty);
  sheet.addEventListener("change", function (e) {
    var el = e.target;
    if (el.name && /-category$/.test(el.name)) {  // "This is…" only applies to food
      var role = el.closest("tr").querySelector("select[name$='-role']");
      if (role) role.hidden = el.value !== "food";
    }
    refreshDirty();
  });
  sheet.addEventListener("submit", function (e) {
    if (!refreshDirty()) { e.preventDefault(); return; }
    // Send only edited cells. Disabled controls aren't submitted.
    cells.forEach(function (el) { if (el.value === orig(el)) el.disabled = true; });
  });
  window.addEventListener("beforeunload", function (e) {
    if (document.body.classList.contains("has-changes") && !sheet.dataset.saving) { e.preventDefault(); e.returnValue = ""; }
  });
  sheet.addEventListener("submit", function () { sheet.dataset.saving = "1"; });

  // ---- ticking rows and bulk actions ----
  var selAll = document.getElementById("sel-all"), selCount = document.getElementById("sel-count");
  var action = document.getElementById("bulk-action"), apply = document.getElementById("bulk-apply");
  function ticks() { return rows.filter(function (tr) { return !tr.hidden; }).map(function (tr) { return tr.querySelector("input[name=sel]"); }); }
  function refreshSel() {
    var n = rows.filter(function (tr) { return tr.querySelector("input[name=sel]").checked; }).length;
    selCount.textContent = n ? n + " ticked:" : "None ticked";
    apply.disabled = n === 0;
    rows.forEach(function (tr) { tr.classList.toggle("ticked", tr.querySelector("input[name=sel]").checked); });
  }
  selAll.addEventListener("change", function () { ticks().forEach(function (c) { c.checked = selAll.checked; }); refreshSel(); });
  rows.forEach(function (tr) { tr.querySelector("input[name=sel]").addEventListener("change", refreshSel); });
  function refreshAction() {
    bulk.querySelectorAll("[data-for]").forEach(function (el) {
      var on = el.dataset.for === action.value;
      el.hidden = !on; el.disabled = !on;
    });
  }
  action.addEventListener("change", refreshAction);
  bulk.addEventListener("submit", function (e) {
    if (refreshDirty() && !window.confirm("You have unsaved changes in the table. Apply this anyway and lose them?")) { e.preventDefault(); return; }
    var n = rows.filter(function (tr) { return tr.querySelector("input[name=sel]").checked; }).length;
    if (action.value === "delete" && !window.confirm("Delete " + n + " item" + (n === 1 ? "" : "s") + " for good? (Marking them used up or binned keeps the history.)")) { e.preventDefault(); return; }
    sheet.dataset.saving = "1";
  });
  refreshAction(); refreshSel();

  // ---- filter ----
  var filter = document.getElementById("sheet-filter"), catSel = document.getElementById("sheet-cat");
  function text(tr) {
    return Array.prototype.map.call(tr.querySelectorAll("input:not([type=checkbox]), select"), function (el) {
      return el.tagName === "SELECT" ? el.options[el.selectedIndex].text : el.value;
    }).join(" ").toLowerCase();
  }
  function refreshFilter() {
    var q = filter.value.trim().toLowerCase(), c = catSel.value;
    rows.forEach(function (tr) {
      var cat = tr.querySelector("select[name$='-category']").value;
      tr.hidden = (q && text(tr).indexOf(q) < 0) || (c && cat !== c);
    });
  }
  filter.addEventListener("input", refreshFilter);
  catSel.addEventListener("change", refreshFilter);

  // ---- sort by clicking a heading ----
  var tbody = sheet.querySelector("tbody");
  sheet.querySelectorAll("th[data-sort]").forEach(function (th) {
    th.tabIndex = 0;
    th.setAttribute("role", "button");
    function sort() {
      var col = th.cellIndex, num = th.dataset.sort === "num";
      var dir = th.getAttribute("aria-sort") === "ascending" ? -1 : 1;
      sheet.querySelectorAll("th[aria-sort]").forEach(function (h) { h.removeAttribute("aria-sort"); });
      th.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
      function val(tr) {
        var el = tr.cells[col].querySelector("input, select");
        if (!el) return "";
        if (el.tagName === "SELECT") return el.hidden ? "" : el.options[el.selectedIndex].text.toLowerCase();
        return num ? parseFloat(el.value) || 0 : el.value.toLowerCase();
      }
      rows.sort(function (a, b) {
        var x = val(a), y = val(b);
        if (x === "" && y !== "") return 1;  // blanks last
        if (y === "" && x !== "") return -1;
        return (x < y ? -1 : x > y ? 1 : 0) * dir;
      });
      rows.forEach(function (tr) { tbody.appendChild(tr); });
    }
    th.addEventListener("click", sort);
    th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); } });
  });
})();
