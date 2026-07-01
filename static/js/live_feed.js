// Live feed — browser camera edition.
// Video is captured from the operator's *device* camera via getUserMedia (so it
// works on a hosted deployment with no server camera). Frames are grabbed to a
// canvas ~1x/second and POSTed to /api/live/analyze for classification. A
// "Capture & Log" button saves the current frame as a persistent inspection via
// the existing /predict endpoint.
(function () {
    "use strict";

    var cfg = document.getElementById("liveConfig");
    var video = document.getElementById("liveVideo");
    var canvas = document.getElementById("liveCanvas");
    var toggleBtn = document.getElementById("cameraToggle");
    var stopBtn = document.getElementById("cameraStop");
    var captureBtn = document.getElementById("cameraCapture");
    var overlay = document.getElementById("cameraOverlay");
    var hint = document.getElementById("cameraHint");
    var stateChip = document.getElementById("cameraState");
    var badge = document.getElementById("liveBadge");
    var badgeText = document.getElementById("liveBadgeText");

    if (!cfg || !video || !toggleBtn || !overlay) {
        return;
    }

    var ANALYZE_URL = cfg.dataset.analyzeUrl;
    var PREDICT_URL = cfg.dataset.predictUrl;
    var CSRF = cfg.dataset.csrf;
    var ANALYZE_INTERVAL = 800; // ms between frames

    var stateLabel = stateChip ? stateChip.querySelector(".live-state-label") : null;
    var toggleLabel = toggleBtn.querySelector(".camera-btn-label");
    var resStatus = document.getElementById("res-status");
    var resClass = document.getElementById("res-class");
    var resConfidence = document.getElementById("res-confidence");
    var resDefects = document.getElementById("res-defects");
    var captureStatus = document.getElementById("captureStatus");

    var state = "off"; // off | connecting | live
    var stream = null;
    var loopTimer = null;
    var analysing = false;

    function setState(next) {
        state = next;
        if (stateChip) stateChip.dataset.state = next;
        overlay.dataset.state = next;

        if (stateLabel) {
            stateLabel.textContent =
                next === "live" ? "Live" :
                next === "connecting" ? "Connecting…" : "Camera off";
        }
        if (next === "live") {
            overlay.classList.add("is-hidden");
            stopBtn.hidden = false;
            captureBtn.hidden = false;
        } else {
            overlay.classList.remove("is-hidden");
            stopBtn.hidden = true;
            captureBtn.hidden = true;
            badge.hidden = true;
        }
        toggleBtn.disabled = next === "connecting";
        if (toggleLabel) {
            toggleLabel.textContent = next === "connecting" ? "Starting…" : "Activate Camera";
        }
        if (hint) {
            hint.textContent = next === "connecting" ? "Requesting camera…" : "Camera is off";
        }
    }

    function fail(message) {
        setState("off");
        if (hint) hint.textContent = message;
    }

    function startCamera() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            fail("Camera needs a secure page. Open the app in its own tab (https), not embedded.");
            return;
        }
        setState("connecting");
        navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false })
            .then(function (mediaStream) {
                stream = mediaStream;
                video.srcObject = mediaStream;
                video.play().catch(function () { /* autoplay attrs handle it */ });
                setState("live");
                scheduleAnalyze();
            })
            .catch(function (err) {
                if (err && err.name === "NotAllowedError") {
                    fail("Camera permission denied. Allow it in your browser and retry.");
                } else if (err && err.name === "NotFoundError") {
                    fail("No camera found on this device.");
                } else {
                    fail("Could not start the camera. If embedded, open the direct app URL.");
                }
            });
    }

    function stopCamera() {
        if (loopTimer) { window.clearTimeout(loopTimer); loopTimer = null; }
        if (stream) {
            stream.getTracks().forEach(function (t) { t.stop(); });
            stream = null;
        }
        video.srcObject = null;
        setState("off");
    }

    function grabBlob(quality) {
        return new Promise(function (resolve) {
            if (!video.videoWidth) { resolve(null); return; }
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
            canvas.toBlob(function (blob) { resolve(blob); }, "image/jpeg", quality || 0.8);
        });
    }

    function renderResult(data) {
        var status = data.status || "";
        badge.hidden = false;
        badge.dataset.status = status;
        var conf = (typeof data.confidence === "number") ? data.confidence + "%" : "";
        var cls = data.predicted_class || "";
        badgeText.textContent = (status ? status.toUpperCase() : "—") + (conf ? " · " + conf : "");
        if (resStatus) resStatus.textContent = status || "—";
        if (resClass) resClass.textContent = cls || "—";
        if (resConfidence) resConfidence.textContent = conf || "—";
        if (resDefects) resDefects.textContent = (data.defects && data.defects.length) ? data.defects.join(", ") : "None";
    }

    function scheduleAnalyze() {
        loopTimer = window.setTimeout(analyzeOnce, ANALYZE_INTERVAL);
    }

    function analyzeOnce() {
        if (state !== "live") return;
        if (analysing) { scheduleAnalyze(); return; }
        analysing = true;
        grabBlob(0.7).then(function (blob) {
            if (!blob) { analysing = false; scheduleAnalyze(); return; }
            var form = new FormData();
            form.append("frame", blob, "frame.jpg");
            return fetch(ANALYZE_URL, { method: "POST", body: form })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (data) { if (data && !data.error) renderResult(data); });
        }).catch(function () { /* transient network/inference error; keep going */ })
          .then(function () { analysing = false; if (state === "live") scheduleAnalyze(); });
    }

    function captureAndLog() {
        if (state !== "live") return;
        captureBtn.disabled = true;
        showCapture("Saving inspection…", "");
        grabBlob(0.85).then(function (blob) {
            if (!blob) { throw new Error("no frame"); }
            var form = new FormData();
            form.append("image", blob, "live_capture.jpg");
            form.append("location", "Live Camera");
            form.append("camera", "LIVE-CAM");
            return fetch(PREDICT_URL, {
                method: "POST",
                body: form,
                headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": CSRF }
            });
        }).then(function (r) { return r.json(); })
          .then(function (data) {
              if (data && data.inspection_id) {
                  showCapture("Logged inspection #" + data.inspection_id +
                      " (" + (data.status || "") + ")", data.detail_url || "");
              } else {
                  showCapture("Could not log inspection.", "");
              }
          })
          .catch(function () { showCapture("Could not log inspection.", ""); })
          .then(function () { captureBtn.disabled = false; });
    }

    function showCapture(message, link) {
        if (!captureStatus) return;
        captureStatus.hidden = false;
        if (link) {
            captureStatus.innerHTML = "";
            captureStatus.appendChild(document.createTextNode(message + " "));
            var a = document.createElement("a");
            a.href = link; a.textContent = "View";
            captureStatus.appendChild(a);
        } else {
            captureStatus.textContent = message;
        }
    }

    toggleBtn.addEventListener("click", function () { if (state === "off") startCamera(); });
    stopBtn.addEventListener("click", stopCamera);
    captureBtn.addEventListener("click", captureAndLog);
    window.addEventListener("beforeunload", function () { if (stream) stopCamera(); });

    setState("off");
})();
