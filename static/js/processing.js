// Polls a background inference job and forwards to the result when it is ready.
(function () {
    var panel = document.getElementById("processing");
    if (!panel) return;

    var statusUrl = panel.dataset.statusUrl;
    var statusText = document.getElementById("processing-status");
    var actions = document.getElementById("processing-actions");

    function showError(message) {
        statusText.textContent = "Analysis failed: " + message;
        if (actions) actions.style.display = "block";
        var spinner = panel.querySelector(".processing-spinner");
        if (spinner) spinner.style.display = "none";
    }

    function poll() {
        fetch(statusUrl, {
            headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" }
        })
            .then(function (response) {
                if (!response.ok) throw new Error("status " + response.status);
                return response.json();
            })
            .then(function (data) {
                if (data.status === "done" && data.result && data.result.detail_url) {
                    window.location.href = data.result.detail_url;
                } else if (data.status === "error") {
                    showError(data.error || "unknown error");
                } else {
                    setTimeout(poll, 1500);
                }
            })
            .catch(function () {
                // Transient network / server hiccup: back off and retry.
                setTimeout(poll, 2500);
            });
    }

    poll();
})();
