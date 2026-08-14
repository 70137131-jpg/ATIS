(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var statusTabs = document.querySelectorAll(".alert-tabs:not(.alert-kind-tabs) .tab");
        var kindTabs = document.querySelectorAll(".alert-kind-tabs .tab");
        var tbody = document.getElementById("alerts-tbody");
        var sectionTitle = document.querySelector(".table-section-title");
        var emptyFilter = document.getElementById("alerts-empty-filter");

        // Status and kind are independent filters; a row must match both.
        var activeStatus = "pending";
        var activeKind = "all";

        var statusLabels = {
            pending: "Pending Alerts",
            acknowledged: "Acknowledged Alerts",
            resolved: "Resolved Alerts",
            all: "All Alerts"
        };
        var kindLabels = {
            defect: " — Defects",
            review: " — Review"
        };

        function applyFilters() {
            if (sectionTitle) {
                sectionTitle.textContent =
                    (statusLabels[activeStatus] || "Alerts") + (kindLabels[activeKind] || "");
            }
            if (!tbody) return;

            var visible = 0;
            tbody.querySelectorAll("tr").forEach(function (row) {
                var status = row.getAttribute("data-status");
                var kind = row.getAttribute("data-kind");
                var match =
                    (activeStatus === "all" || status === activeStatus) &&
                    (activeKind === "all" || kind === activeKind);
                row.style.display = match ? "" : "none";
                if (match && status && !row.classList.contains("alert-detail-row")) visible += 1;
            });
            if (emptyFilter) emptyFilter.style.display = visible === 0 ? "flex" : "none";
        }

        function bind(tabs, attribute, onSelect) {
            tabs.forEach(function (tab) {
                tab.addEventListener("click", function () {
                    tabs.forEach(function (other) { other.classList.remove("active"); });
                    tab.classList.add("active");
                    onSelect(tab.getAttribute(attribute));
                    applyFilters();
                });
            });
        }

        bind(statusTabs, "data-tab", function (value) { activeStatus = value; });
        bind(kindTabs, "data-kind", function (value) { activeKind = value; });

        applyFilters();
    });
})();
