// Live feed camera control.
// The camera is a *server-side* OpenCV stream (`/live/stream`, an MJPEG endpoint).
// Pointing the <img> at that URL opens the webcam; clearing the src aborts the
// request so the server releases the camera (cap.release()). This lets the demo
// operator start/stop the feed with a single button instead of it auto-starting.
(function () {
    "use strict";

    var video = document.getElementById("liveVideo");
    var toggleBtn = document.getElementById("cameraToggle");
    var stopBtn = document.getElementById("cameraStop");
    var overlay = document.getElementById("cameraOverlay");
    var hint = document.getElementById("cameraHint");
    var stateChip = document.getElementById("cameraState");

    if (!video || !toggleBtn || !overlay) {
        return;
    }

    var stateLabel = stateChip ? stateChip.querySelector(".live-state-label") : null;
    var toggleLabel = toggleBtn.querySelector(".camera-btn-label");
    var streamUrl = video.dataset.stream;
    var state = "off"; // off | connecting | live
    var revealTimer = null;

    function setState(next) {
        state = next;

        if (stateChip) {
            stateChip.dataset.state = next;
        }
        overlay.dataset.state = next;

        if (stateLabel) {
            stateLabel.textContent =
                next === "live" ? "Live Python stream" :
                next === "connecting" ? "Connecting…" :
                "Camera off";
        }

        if (next === "live") {
            overlay.classList.add("is-hidden");
            stopBtn.hidden = false;
        } else {
            overlay.classList.remove("is-hidden");
            stopBtn.hidden = true;
        }

        toggleBtn.disabled = next === "connecting";
        if (toggleLabel) {
            toggleLabel.textContent = next === "connecting" ? "Connecting…" : "Activate Camera";
        }
        if (hint && next !== "off") {
            hint.textContent = next === "connecting" ? "Starting camera…" : "Camera is on";
        } else if (hint) {
            hint.textContent = "Camera is off";
        }
    }

    function startCamera() {
        setState("connecting");
        // Cache-bust so each activation opens a fresh stream connection.
        var sep = streamUrl.indexOf("?") === -1 ? "?" : "&";
        video.src = streamUrl + sep + "t=" + Date.now();

        // MJPEG 'load' fires when the first frame arrives in most browsers; add a
        // short optimistic reveal so the demo never sticks on "Connecting".
        window.clearTimeout(revealTimer);
        revealTimer = window.setTimeout(function () {
            if (state === "connecting") {
                setState("live");
            }
        }, 1500);
    }

    function stopCamera() {
        window.clearTimeout(revealTimer);
        // Dropping the src aborts the MJPEG request -> server releases the camera.
        video.removeAttribute("src");
        video.src = "";
        setState("off");
    }

    video.addEventListener("load", function () {
        if (state === "connecting") {
            setState("live");
        }
    });

    video.addEventListener("error", function () {
        // Ignore the spurious error from clearing src on stop (state is already "off").
        if (state !== "off") {
            window.clearTimeout(revealTimer);
            setState("off");
            if (hint) {
                hint.textContent = "Could not reach the camera. Press to try again.";
            }
        }
    });

    toggleBtn.addEventListener("click", function () {
        if (state === "off") {
            startCamera();
        }
    });

    stopBtn.addEventListener("click", stopCamera);

    // Release the camera if the operator navigates away with the feed running.
    window.addEventListener("beforeunload", function () {
        if (state !== "off") {
            video.src = "";
        }
    });

    setState("off");
})();
