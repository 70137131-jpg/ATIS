(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var exportBtn = document.getElementById("history-export-btn");
        if (exportBtn) {
            exportBtn.addEventListener("click", function () {
                exportBtn.classList.add("is-loading");
                setTimeout(function () { exportBtn.classList.remove("is-loading"); }, 800);
            });
        }
    });
})();
