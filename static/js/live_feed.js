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
    var boxCanvas = document.getElementById("liveBoxCanvas");
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
    var lastSoundStatus = "";
    var lastUnsafeSoundAt = 0;
    var UNSAFE_SOUND_COOLDOWN = 8000;

    function clearFrameBoxes() {
        if (!boxCanvas) return;
        var ctx = boxCanvas.getContext("2d");
        ctx.clearRect(0, 0, boxCanvas.width, boxCanvas.height);
    }

    function syncBoxCanvas() {
        if (!boxCanvas) return null;
        var rect = boxCanvas.getBoundingClientRect();
        var dpr = window.devicePixelRatio || 1;
        var width = Math.max(1, Math.round(rect.width * dpr));
        var height = Math.max(1, Math.round(rect.height * dpr));
        if (boxCanvas.width !== width || boxCanvas.height !== height) {
            boxCanvas.width = width;
            boxCanvas.height = height;
        }
        var ctx = boxCanvas.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, rect.width, rect.height);
        return { ctx: ctx, width: rect.width, height: rect.height };
    }

    function visibleVideoRect(width, height) {
        var sourceW = video.videoWidth || width;
        var sourceH = video.videoHeight || height;
        var sourceRatio = sourceW / sourceH;
        var canvasRatio = width / height;
        var fit = window.getComputedStyle(video).objectFit || "contain";
        var rect = { x: 0, y: 0, width: width, height: height };

        if (fit === "contain" && canvasRatio > sourceRatio) {
            rect.width = height * sourceRatio;
            rect.x = (width - rect.width) / 2;
        } else if (fit === "contain") {
            rect.height = width / sourceRatio;
            rect.y = (height - rect.height) / 2;
        } else if (fit === "cover" && canvasRatio > sourceRatio) {
            rect.height = width / sourceRatio;
            rect.y = (height - rect.height) / 2;
        } else if (fit === "cover") {
            rect.width = height * sourceRatio;
            rect.x = (width - rect.width) / 2;
        }

        return rect;
    }

    function normalizeBox(box) {
        if (!box) return null;
        if (Array.isArray(box.bbox)) {
            return {
                x1: Number(box.bbox[0]),
                y1: Number(box.bbox[1]),
                x2: Number(box.bbox[2]),
                y2: Number(box.bbox[3])
            };
        }
        if ("x" in box && "y" in box && "width" in box && "height" in box) {
            return {
                x1: Number(box.x),
                y1: Number(box.y),
                x2: Number(box.x) + Number(box.width),
                y2: Number(box.y) + Number(box.height)
            };
        }
        return {
            x1: Number(box.x1),
            y1: Number(box.y1),
            x2: Number(box.x2),
            y2: Number(box.y2)
        };
    }

    function drawFrameBoxes(boxes) {
        var canvasState = syncBoxCanvas();
        if (!canvasState || !Array.isArray(boxes) || !boxes.length) return;

        var ctx = canvasState.ctx;
        var videoRect = visibleVideoRect(canvasState.width, canvasState.height);

        boxes.forEach(function (box) {
            var normalized = normalizeBox(box);
            if (!normalized) return;

            var boxMax = Math.max(normalized.x1, normalized.y1, normalized.x2, normalized.y2);
            var x1 = normalized.x1;
            var y1 = normalized.y1;
            var x2 = normalized.x2;
            var y2 = normalized.y2;
            if (boxMax <= 1) {
                x1 *= videoRect.width;
                x2 *= videoRect.width;
                y1 *= videoRect.height;
                y2 *= videoRect.height;
            }

            x1 += videoRect.x;
            x2 += videoRect.x;
            y1 += videoRect.y;
            y2 += videoRect.y;

            var color = box.status === "safe" ? "#22c55e" : "#ef4444";
            var width = Math.max(2, x2 - x1);
            var height = Math.max(2, y2 - y1);
            var label = [
                box.label || box.predicted_class || "tire",
                box.confidence ? box.confidence + "%" : "",
                // Heuristic localizer boxes are estimates, not trained detections.
                box.source === "heuristic" ? "(est.)" : "",
            ]
                .filter(Boolean)
                .join(" ");

            ctx.lineWidth = 3;
            ctx.strokeStyle = color;
            ctx.fillStyle = "rgba(6, 19, 14, 0.76)";
            ctx.strokeRect(x1, y1, width, height);

            if (label) {
                ctx.font = "700 13px system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
                var metrics = ctx.measureText(label);
                var labelW = Math.min(metrics.width + 16, Math.max(width, 80));
                var labelY = Math.max(0, y1 - 28);
                ctx.fillStyle = color;
                ctx.fillRect(x1, labelY, labelW, 24);
                ctx.fillStyle = "#ffffff";
                ctx.fillText(label, x1 + 8, labelY + 16);
            }
        });
    }

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
            clearFrameBoxes();
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
        var now = Date.now();
        badge.hidden = false;
        badge.dataset.status = status;
        var conf = (typeof data.confidence === "number") ? data.confidence + "%" : "";
        var cls = data.predicted_class || "";
        var isNotTyre = cls === "not_tyre";
        badgeText.textContent = isNotTyre
            ? "NOT A TYRE"
            : (status ? status.toUpperCase() : "—") + (conf ? " · " + conf : "");
        if (resStatus) resStatus.textContent = status || "—";
        if (resClass) resClass.textContent = isNotTyre ? "Not a tyre" : (cls || "—");
        if (resConfidence) resConfidence.textContent = isNotTyre ? "—" : (conf || "—");
        if (resDefects) resDefects.textContent = (data.defects && data.defects.length) ? data.defects.join(", ") : "None";
        drawFrameBoxes(data.boxes || data.bounding_boxes || data.detections || []);

        if (
            status === "unsafe" &&
            !isNotTyre &&
            window.ATISAlertSound &&
            (lastSoundStatus !== "unsafe" || now - lastUnsafeSoundAt > UNSAFE_SOUND_COOLDOWN)
        ) {
            window.ATISAlertSound.play("critical");
            lastUnsafeSoundAt = now;
        }
        lastSoundStatus = status;
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
            return fetch(ANALYZE_URL, {
                method: "POST",
                body: form,
                headers: { "X-CSRFToken": CSRF }
            })
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
                  var resultLabel = data.predicted_class === "not_tyre" ? "not a tyre" : (data.status || "");
                  showCapture("Logged inspection #" + data.inspection_id +
                      " (" + resultLabel + ")", data.dashboard_url || data.detail_url || "");
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
            a.href = link; a.textContent = "View Dashboard";
            captureStatus.appendChild(a);
        } else {
            captureStatus.textContent = message;
        }
    }

    toggleBtn.addEventListener("click", function () { if (state === "off") startCamera(); });
    stopBtn.addEventListener("click", stopCamera);
    captureBtn.addEventListener("click", captureAndLog);
    window.addEventListener("resize", clearFrameBoxes);
    window.addEventListener("beforeunload", function () { if (stream) stopCamera(); });

    setState("off");
})();
