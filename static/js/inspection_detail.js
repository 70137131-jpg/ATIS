(function () {
    "use strict";

    var dataEl = document.getElementById("insp-boxes-data");
    var img = document.getElementById("insp-image");
    var canvas = document.getElementById("insp-bbox-canvas");
    if (!dataEl || !img || !canvas) return;

    var boxes = [];
    try {
        boxes = JSON.parse(dataEl.textContent) || [];
    } catch (_err) {
        boxes = [];
    }
    if (!Array.isArray(boxes) || !boxes.length) return;

    var severityColors = { High: "#dc2626", Medium: "#f59e0b", Low: "#eab308" };

    function draw() {
        var w = img.clientWidth;
        var h = img.clientHeight;
        if (!w || !h) return;
        canvas.width = w;
        canvas.height = h;
        canvas.style.width = w + "px";
        canvas.style.height = h + "px";
        var ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, w, h);
        boxes.forEach(function (box) {
            var b = box.bbox || [];
            if (b.length < 4) return;
            var x1 = b[0], y1 = b[1], x2 = b[2], y2 = b[3];
            if (Math.max(x1, y1, x2, y2) <= 1) {
                x1 *= w; x2 *= w; y1 *= h; y2 *= h;
            }
            var color = severityColors[box.severity] || severityColors.Medium;
            ctx.lineWidth = 3;
            ctx.strokeStyle = color;
            ctx.fillStyle = color;
            ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
            var label = box.label || "";
            if (box.confidence !== undefined) label += " " + box.confidence + "%";
            // Heuristic localizer boxes are estimates, not trained detections.
            if (box.source === "heuristic") label += " (est.)";
            if (label) {
                ctx.font = "600 12px Inter, sans-serif";
                var lw = ctx.measureText(label).width + 12;
                var lh = 20;
                var ly = y1 > lh ? y1 - lh : y1;
                ctx.fillRect(x1, ly, lw, lh);
                ctx.fillStyle = "#ffffff";
                ctx.fillText(label, x1 + 6, ly + 14);
            }
        });
    }

    if (img.complete && img.naturalWidth) draw();
    else img.addEventListener("load", draw);
    window.addEventListener("resize", draw);
})();
