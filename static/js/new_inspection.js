(function () {
    "use strict";

    var dropZone = document.getElementById("drop-zone");
    var fileInput = document.getElementById("image-input");
    var placeholder = document.getElementById("drop-placeholder");
    var preview = document.getElementById("image-preview");
    var previewStage = document.getElementById("preview-stage");
    var previewImg = document.getElementById("preview-img");
    var bboxCanvas = document.getElementById("bbox-canvas");
    var removeBtn = document.getElementById("remove-btn");
    var form = document.getElementById("inspect-form");
    var submitBtn = document.getElementById("submit-btn");
    var resultPanel = document.getElementById("analysis-result");
    var resultStatus = document.getElementById("analysis-status");
    var resultConfidence = document.getElementById("analysis-confidence");
    var resultDefects = document.getElementById("analysis-defects");
    var detailLink = document.getElementById("detail-link");
    var plateInput = document.getElementById("plate-input");
    var anprBtn = document.getElementById("anpr-btn");
    var anprStatus = document.getElementById("anpr-status");
    if (!dropZone || !fileInput || !form) return;

    var latestBoxes = [];
    var severityColors = {
        Critical: "#ef4444",
        Medium: "#f97316",
        Low: "#facc15"
    };

    function normalizeSeverity(value) {
        var severity = String(value || "Low").toLowerCase();
        if (severity === "critical" || severity === "high") return "Critical";
        if (severity === "medium" || severity === "moderate") return "Medium";
        return "Low";
    }

    function clearBoxes() {
        latestBoxes = [];
        if (!bboxCanvas) return;
        var ctx = bboxCanvas.getContext("2d");
        ctx.clearRect(0, 0, bboxCanvas.width, bboxCanvas.height);
    }

    function showPreview(file) {
        clearBoxes();
        resultPanel.style.display = "none";
        var reader = new FileReader();
        reader.onload = function (e) {
            previewImg.src = e.target.result;
            placeholder.style.display = "none";
            preview.style.display = "flex";
        };
        reader.readAsDataURL(file);
    }

    function setSubmitLoading(isLoading) {
        submitBtn.querySelector(".btn-text").style.display = isLoading ? "none" : "inline";
        submitBtn.querySelector(".btn-loading").style.display = isLoading ? "inline-flex" : "none";
        submitBtn.disabled = isLoading;
    }

    function setAnprStatus(message, state) {
        if (!anprStatus) return;
        anprStatus.textContent = message;
        anprStatus.classList.toggle("is-success", state === "success");
        anprStatus.classList.toggle("is-error", state === "error");
    }

    function setAnprLoading(isLoading) {
        if (!anprBtn) return;
        anprBtn.disabled = isLoading;
        anprBtn.textContent = isLoading ? "Reading..." : "Read Plate";
    }

    function normalizeBox(box) {
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

    function getImageRectInsideStage() {
        var stageRect = previewStage.getBoundingClientRect();
        var imageRect = previewImg.getBoundingClientRect();
        return {
            left: imageRect.left - stageRect.left,
            top: imageRect.top - stageRect.top,
            width: imageRect.width,
            height: imageRect.height
        };
    }

    function resizeCanvasToStage() {
        var rect = previewStage.getBoundingClientRect();
        var scale = window.devicePixelRatio || 1;
        bboxCanvas.style.width = rect.width + "px";
        bboxCanvas.style.height = rect.height + "px";
        bboxCanvas.width = Math.round(rect.width * scale);
        bboxCanvas.height = Math.round(rect.height * scale);
        var ctx = bboxCanvas.getContext("2d");
        ctx.setTransform(scale, 0, 0, scale, 0, 0);
        return ctx;
    }

    function drawBoxes(boxes) {
        latestBoxes = Array.isArray(boxes) ? boxes : [];
        if (!previewImg.complete || !previewImg.naturalWidth) {
            previewImg.addEventListener("load", function () { drawBoxes(latestBoxes); }, { once: true });
            return;
        }
        var ctx = resizeCanvasToStage();
        ctx.clearRect(0, 0, bboxCanvas.width, bboxCanvas.height);
        var imageRect = getImageRectInsideStage();
        var scaleX = imageRect.width / previewImg.naturalWidth;
        var scaleY = imageRect.height / previewImg.naturalHeight;
        latestBoxes.forEach(function (box) {
            var normalized = normalizeBox(box);
            if ([normalized.x1, normalized.y1, normalized.x2, normalized.y2].some(Number.isNaN)) return;
            var boxMax = Math.max(normalized.x1, normalized.y1, normalized.x2, normalized.y2);
            if (boxMax <= 1) {
                normalized.x1 *= previewImg.naturalWidth;
                normalized.x2 *= previewImg.naturalWidth;
                normalized.y1 *= previewImg.naturalHeight;
                normalized.y2 *= previewImg.naturalHeight;
            }
            var severity = normalizeSeverity(box.severity || box.level);
            var color = severityColors[severity] || severityColors.Low;
            var x = imageRect.left + normalized.x1 * scaleX;
            var y = imageRect.top + normalized.y1 * scaleY;
            var width = (normalized.x2 - normalized.x1) * scaleX;
            var height = (normalized.y2 - normalized.y1) * scaleY;
            var label = [severity, box.label].filter(Boolean).join(" - ");
            ctx.lineWidth = 3;
            ctx.strokeStyle = color;
            ctx.fillStyle = color;
            ctx.strokeRect(x, y, width, height);
            if (label) {
                ctx.font = "600 12px Inter, sans-serif";
                var labelWidth = ctx.measureText(label).width + 12;
                var labelHeight = 22;
                var labelY = y > labelHeight ? y - labelHeight : y;
                ctx.fillRect(x, labelY, labelWidth, labelHeight);
                ctx.fillStyle = severity === "Low" ? "#111827" : "#ffffff";
                ctx.fillText(label, x + 6, labelY + 15);
            }
        });
    }

    function renderResult(data) {
        var defects = Array.isArray(data.defects) ? data.defects : [];
        resultStatus.textContent = (data.status || "complete").toUpperCase() + " result";
        resultConfidence.textContent = data.confidence !== undefined ? data.confidence + "% confidence" : "";
        resultDefects.replaceChildren();
        if (defects.length) {
            defects.forEach(function (defect) {
                var tag = document.createElement("span");
                tag.className = "result-defect";
                tag.textContent = defect;
                resultDefects.appendChild(tag);
            });
        } else {
            var empty = document.createElement("span");
            empty.className = "result-empty";
            empty.textContent = "No defects returned";
            resultDefects.appendChild(empty);
        }
        if (data.plate) {
            var plateTag = document.createElement("span");
            plateTag.className = "result-defect result-plate";
            plateTag.textContent = "Plate: " + data.plate;
            resultDefects.appendChild(plateTag);
            if (plateInput && !plateInput.value) {
                plateInput.value = data.plate;
            }
            setAnprStatus(
                data.plate_source === "manual"
                    ? "Manual plate saved."
                    : "Auto-read plate saved" + (data.plate_confidence !== null && data.plate_confidence !== undefined ? " (" + data.plate_confidence + "%)." : "."),
                "success"
            );
        } else {
            setAnprStatus("No plate was read; inspection saved without a plate.", "");
        }
        if (data.detail_url) {
            detailLink.href = data.detail_url;
            detailLink.style.display = "inline-flex";
        } else {
            detailLink.style.display = "none";
        }
        resultPanel.style.display = "block";
    }

    dropZone.addEventListener("click", function (e) {
        if (e.target === removeBtn || removeBtn.contains(e.target)) return;
        fileInput.click();
    });

    ["dragenter", "dragover"].forEach(function (evt) {
        dropZone.addEventListener(evt, function (e) {
            e.preventDefault();
            dropZone.classList.add("drag-over");
        });
    });

    ["dragleave", "drop"].forEach(function (evt) {
        dropZone.addEventListener(evt, function (e) {
            e.preventDefault();
            dropZone.classList.remove("drag-over");
        });
    });

    dropZone.addEventListener("drop", function (e) {
        var files = e.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            showPreview(files[0]);
        }
    });

    fileInput.addEventListener("change", function () {
        if (fileInput.files.length > 0) showPreview(fileInput.files[0]);
    });

    removeBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        fileInput.value = "";
        preview.style.display = "none";
        placeholder.style.display = "flex";
        resultPanel.style.display = "none";
        setAnprStatus("Leave blank to auto-read during analysis.", "");
        clearBoxes();
    });

    if (anprBtn) {
        anprBtn.addEventListener("click", async function () {
            if (!fileInput.files.length) {
                setAnprStatus("Choose an image before reading the plate.", "error");
                return;
            }
            setAnprLoading(true);
            setAnprStatus("Reading plate from image...", "");
            try {
                var formData = new FormData();
                formData.append("image", fileInput.files[0]);
                var csrfInput = form.querySelector("input[name='csrf_token']");
                if (csrfInput) formData.append("csrf_token", csrfInput.value);
                var response = await fetch(anprBtn.dataset.anprUrl, {
                    method: "POST",
                    body: formData,
                    headers: {
                        Accept: "application/json",
                        "X-Requested-With": "XMLHttpRequest"
                    }
                });
                var data = await response.json();
                if (!response.ok) throw new Error(data.error || "Plate read failed");
                if (data.plate) {
                    plateInput.value = data.plate;
                    if (data.needs_review) {
                        setAnprStatus(
                            "Low-confidence candidate " + data.plate + (data.confidence !== null && data.confidence !== undefined ? " (" + data.confidence + "%, threshold " + data.min_confidence + "%)." : "."),
                            "error"
                        );
                    } else {
                        setAnprStatus(
                            "Detected " + data.plate + (data.confidence !== null && data.confidence !== undefined ? " (" + data.confidence + "%)." : "."),
                            "success"
                        );
                    }
                } else {
                    setAnprStatus("No readable plate found. Enter it manually or submit without one.", "error");
                }
            } catch (error) {
                setAnprStatus(error.message, "error");
            } finally {
                setAnprLoading(false);
            }
        });
    }

    window.addEventListener("resize", function () {
        if (latestBoxes.length) drawBoxes(latestBoxes);
    });

    function delay(ms) {
        return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }

    // Async-inference mode: /predict returns 202 with a status_url; poll it until
    // the background job finishes, then use its result (same shape as the sync
    // response). Synchronous mode returns the result directly and skips this.
    async function pollJob(statusUrl) {
        for (;;) {
            await delay(1500);
            var resp = await fetch(statusUrl, {
                headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" }
            });
            if (!resp.ok) throw new Error("Job status failed with status " + resp.status);
            var body = await resp.json();
            if (body.status === "done") return body.result;
            if (body.status === "error") throw new Error(body.error || "Analysis failed");
        }
    }

    form.addEventListener("submit", async function (e) {
        e.preventDefault();
        setSubmitLoading(true);
        resultPanel.style.display = "none";
        clearBoxes();
        try {
            var response = await fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                headers: {
                    Accept: "application/json",
                    "X-Requested-With": "XMLHttpRequest"
                }
            });
            if (!response.ok) throw new Error("Analysis failed with status " + response.status);
            var data = await response.json();
            if (data && data.status_url) {
                data = await pollJob(data.status_url);
            }
            renderResult(data);
            drawBoxes(data.bounding_boxes || data.boxes || data.detections || []);
        } catch (error) {
            resultStatus.textContent = "Analysis failed";
            resultConfidence.textContent = "";
            var errorMessage = document.createElement("span");
            errorMessage.className = "result-empty";
            errorMessage.textContent = error.message;
            resultDefects.replaceChildren(errorMessage);
            detailLink.style.display = "none";
            resultPanel.style.display = "block";
        } finally {
            setSubmitLoading(false);
        }
    });
})();
