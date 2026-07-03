(function () {
    "use strict";

    var chartInstance = null;

    async function fetchChartData(type, from, to) {
        var endpoints = {
            "safety-trend": "/api/reports/safety-trend",
            "defect-distribution": "/api/reports/defect-distribution",
            "daily-summary": "/api/reports/daily-summary"
        };
        var resp = await fetch(endpoints[type] + "?from=" + from + "&to=" + to);
        if (!resp.ok) throw new Error("API error: " + resp.status);
        return await resp.json();
    }

    function buildSafetyTrend(data) {
        return {
            type: "line",
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: "Safe",
                        data: data.safe,
                        borderColor: "#10b981",
                        backgroundColor: "rgba(16,185,129,0.1)",
                        fill: true,
                        tension: 0.35,
                        pointRadius: 4,
                        pointBackgroundColor: "#10b981"
                    },
                    {
                        label: "Unsafe",
                        data: data.unsafe,
                        borderColor: "#ef4444",
                        backgroundColor: "rgba(239,68,68,0.1)",
                        fill: true,
                        tension: 0.35,
                        pointRadius: 4,
                        pointBackgroundColor: "#ef4444"
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "top" } },
                scales: { y: { beginAtZero: true, title: { display: true, text: "Inspections" } } }
            }
        };
    }

    function buildDefectDistribution(data) {
        var colors = ["#4285f4", "#ef4444", "#f59e0b", "#8b5cf6", "#10b981", "#ec4899", "#06b6d4", "#f97316"];
        return {
            type: "doughnut",
            data: {
                labels: data.labels,
                datasets: [{
                    data: data.values,
                    backgroundColor: colors.slice(0, data.labels.length),
                    borderWidth: 2,
                    borderColor: "#fff"
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "right" } }
            }
        };
    }

    function buildDailySummary(data) {
        return {
            type: "bar",
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: "Total Inspections",
                        data: data.total,
                        backgroundColor: "rgba(66,133,244,0.7)",
                        borderRadius: 4
                    },
                    {
                        label: "Unsafe Detected",
                        data: data.unsafe,
                        backgroundColor: "rgba(239,68,68,0.7)",
                        borderRadius: 4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "top" } },
                scales: { y: { beginAtZero: true, title: { display: true, text: "Count" } } }
            }
        };
    }

    function isDataEmpty(data) {
        if (data.safe) return data.safe.every(function (v) { return v === 0; }) && data.unsafe.every(function (v) { return v === 0; });
        if (data.values) return data.values.length === 0;
        if (data.total) return data.total.every(function (v) { return v === 0; });
        return true;
    }

    function showOnly(state) {
        ["chart-placeholder", "chart-canvas-wrapper", "chart-no-data", "chart-loading"].forEach(function (id) {
            var el = document.getElementById(id);
            if (!el) return;
            el.style.display = id === state ? (id === "chart-canvas-wrapper" ? "block" : "flex") : "none";
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        var generateBtn = document.getElementById("generate-btn");
        var exportBtn = document.getElementById("export-pdf-btn");
        var exportCsvBtn = document.getElementById("export-csv-btn");
        var exportFeedbackBtn = document.getElementById("export-feedback-btn");
        if (!generateBtn || !exportBtn) return;

        generateBtn.addEventListener("click", async function () {
            var type = document.getElementById("report-type").value;
            var from = document.getElementById("date-from").value;
            var to = document.getElementById("date-to").value;
            var titleMap = {
                "safety-trend": "Safety Trend",
                "defect-distribution": "Defect Distribution",
                "daily-summary": "Daily Summary"
            };
            generateBtn.classList.add("is-loading");
            generateBtn.disabled = true;
            document.getElementById("chart-card-title").textContent = titleMap[type] || "Report";
            showOnly("chart-loading");
            if (chartInstance) {
                chartInstance.destroy();
                chartInstance = null;
            }
            try {
                var data = await fetchChartData(type, from, to);
                if (isDataEmpty(data)) {
                    showOnly("chart-no-data");
                    return;
                }
                var wrapper = document.getElementById("chart-canvas-wrapper");
                wrapper.style.height = "380px";
                showOnly("chart-canvas-wrapper");
                var config = type === "defect-distribution"
                    ? buildDefectDistribution(data)
                    : type === "daily-summary"
                        ? buildDailySummary(data)
                        : buildSafetyTrend(data);
                chartInstance = new Chart(document.getElementById("report-chart"), config);
            } catch (err) {
                showOnly("chart-no-data");
                document.querySelector("#chart-no-data p").textContent = "Error loading data: " + err.message;
                console.error("Report error:", err);
            } finally {
                generateBtn.classList.remove("is-loading");
                generateBtn.disabled = false;
            }
        });

        function exportReport(button, endpoint) {
            button.classList.add("is-loading");
            var from = document.getElementById("date-from").value;
            var to = document.getElementById("date-to").value;
            window.location.href = endpoint + "?from=" + from + "&to=" + to;
            window.setTimeout(function () { button.classList.remove("is-loading"); }, 900);
        }

        exportBtn.addEventListener("click", function () {
            exportReport(exportBtn, "/api/reports/export-pdf");
        });
        if (exportCsvBtn) {
            exportCsvBtn.addEventListener("click", function () {
                exportReport(exportCsvBtn, "/api/reports/export-csv");
            });
        }
        if (exportFeedbackBtn) {
            exportFeedbackBtn.addEventListener("click", function () {
                exportReport(exportFeedbackBtn, "/api/model-feedback/export");
            });
        }
    });
})();
