(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var tabs = document.querySelectorAll(".alert-tabs .tab");
        var tbody = document.getElementById("alerts-tbody");
        var sectionTitle = document.querySelector(".table-section-title");
        var emptyFilter = document.getElementById("alerts-empty-filter");

        function filterByTab(activeTab) {
            var filter = activeTab.getAttribute("data-tab");
            tabs.forEach(function (tab) { tab.classList.remove("active"); });
            activeTab.classList.add("active");

            var labels = {
                pending: "Pending Alerts",
                acknowledged: "Acknowledged Alerts",
                resolved: "Resolved Alerts",
                all: "All Alerts"
            };
            if (sectionTitle) sectionTitle.textContent = labels[filter] || "Alerts";
            if (!tbody) return;

            var visible = 0;
            tbody.querySelectorAll("tr").forEach(function (row) {
                var status = row.getAttribute("data-status");
                var match = filter === "all" || status === filter;
                row.style.display = match ? "" : "none";
                if (match && status && !row.classList.contains("alert-detail-row")) visible += 1;
            });
            if (emptyFilter) emptyFilter.style.display = visible === 0 ? "flex" : "none";
        }

        tabs.forEach(function (tab) {
            tab.addEventListener("click", function () { filterByTab(tab); });
        });
    });
})();
