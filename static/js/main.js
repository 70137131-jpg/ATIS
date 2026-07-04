/**
 * main.js — Dashboard interactivity
 */
window.ATISAlertSound = (function () {
    "use strict";

    var STORAGE_KEY = "atis_alert_sound_muted";
    var audioContext = null;
    var unlocked = false;
    var queuedTone = null;

    function isMuted() {
        return window.localStorage.getItem(STORAGE_KEY) === "1";
    }

    function setMuted(muted) {
        window.localStorage.setItem(STORAGE_KEY, muted ? "1" : "0");
        updateToggle();
    }

    function context() {
        var AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) return null;
        if (!audioContext) audioContext = new AudioContext();
        return audioContext;
    }

    function unlock() {
        if (unlocked || isMuted()) return;
        var ctx = context();
        if (!ctx) return;
        if (ctx.state === "suspended") {
            ctx.resume().catch(function () { /* Browser will allow this after interaction. */ });
        }
        unlocked = true;
        if (queuedTone) {
            var tone = queuedTone;
            queuedTone = null;
            window.setTimeout(function () { play(tone); }, 120);
        }
    }

    function toneSteps(kind) {
        if (kind === "critical") {
            return [
                { freq: 880, start: 0.00, duration: 0.16 },
                { freq: 660, start: 0.20, duration: 0.16 },
                { freq: 880, start: 0.40, duration: 0.22 }
            ];
        }
        return [
            { freq: 740, start: 0.00, duration: 0.12 },
            { freq: 580, start: 0.16, duration: 0.16 }
        ];
    }

    function play(kind) {
        if (isMuted()) return false;
        var ctx = context();
        if (!ctx) return false;
        if (ctx.state === "suspended" || !unlocked) {
            queuedTone = kind || "warning";
            return false;
        }

        var now = ctx.currentTime;
        var master = ctx.createGain();
        master.gain.setValueAtTime(0.0001, now);
        master.gain.exponentialRampToValueAtTime(0.18, now + 0.025);
        master.gain.exponentialRampToValueAtTime(0.0001, now + 0.8);
        master.connect(ctx.destination);

        toneSteps(kind).forEach(function (step) {
            var oscillator = ctx.createOscillator();
            var envelope = ctx.createGain();
            var start = now + step.start;
            var end = start + step.duration;
            oscillator.type = "triangle";
            oscillator.frequency.setValueAtTime(step.freq, start);
            envelope.gain.setValueAtTime(0.0001, start);
            envelope.gain.exponentialRampToValueAtTime(1, start + 0.018);
            envelope.gain.exponentialRampToValueAtTime(0.0001, end);
            oscillator.connect(envelope);
            envelope.connect(master);
            oscillator.start(start);
            oscillator.stop(end + 0.04);
        });
        return true;
    }

    function updateToggle() {
        var toggle = document.getElementById("alert-sound-toggle");
        if (!toggle) return;
        var muted = isMuted();
        toggle.classList.toggle("is-muted", muted);
        toggle.setAttribute("aria-pressed", muted ? "false" : "true");
        toggle.setAttribute("title", muted ? "Alert sound off" : "Alert sound on");
        toggle.setAttribute("aria-label", muted ? "Alert sound off" : "Alert sound on");
    }

    function bind() {
        updateToggle();
        var toggle = document.getElementById("alert-sound-toggle");
        if (toggle) {
            toggle.addEventListener("click", function () {
                var muted = !isMuted();
                setMuted(muted);
                if (!muted) {
                    unlock();
                    play("warning");
                }
            });
        }
        ["pointerdown", "keydown", "touchstart"].forEach(function (eventName) {
            document.addEventListener(eventName, unlock, { once: true, passive: true });
        });
    }

    return {
        bind: bind,
        play: play,
        isMuted: isMuted,
        unlock: unlock
    };
})();

document.addEventListener("DOMContentLoaded", () => {
    window.ATISAlertSound.bind();

    /* ----- Plate search filter ----- */
    const searchInput = document.getElementById("search-plate");
    const statusFilter = document.getElementById("status-filter");
    const tbody = document.getElementById("inspection-tbody");

    function filterTable() {
        if (!tbody) return;
        const query = (searchInput?.value || "").toLowerCase();
        const status = statusFilter?.value || "all";
        let visible = 0;

        tbody.querySelectorAll("tr").forEach(row => {
            const plate = (row.querySelector(".cell-plate")?.textContent || "").toLowerCase();
            const badge = row.querySelector(".badge");
            const rowStatus = badge?.classList.contains("badge-safe") ? "safe" :
                badge?.classList.contains("badge-unsafe") ? "unsafe" : "";

            const matchPlate = !query || plate.includes(query);
            const matchStatus = status === "all" || rowStatus === status;

            const match = matchPlate && matchStatus;
            row.style.display = match ? "" : "none";
            if (match && row.querySelector(".cell-plate")) visible++;
        });

        const emptyFilter = document.getElementById("dashboard-empty-filter");
        if (emptyFilter) emptyFilter.style.display = visible === 0 ? "flex" : "none";
    }

    if (searchInput) searchInput.addEventListener("input", filterTable);
    if (statusFilter) statusFilter.addEventListener("change", filterTable);

    /* ----- Refresh button ----- */
    const refreshBtn = document.getElementById("refresh-btn");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
            refreshBtn.disabled = true;
            refreshBtn.classList.add("is-loading");
            setTimeout(() => {
                location.reload();
            }, 600);
        });
    }

    /* ----- Notification dropdown ----- */
    const notifToggle = document.getElementById("notification-toggle");
    const notifDropdown = document.getElementById("notification-dropdown");
    const notifBadge = document.querySelector(".notification-badge");
    const pendingAlertCount = Number((notifBadge?.textContent || "0").trim()) || 0;

    if (pendingAlertCount > 0) {
        window.ATISAlertSound.play(pendingAlertCount >= 3 ? "critical" : "warning");
    }

    if (notifToggle && notifDropdown) {
        notifToggle.addEventListener("click", (e) => {
            e.stopPropagation();
            notifDropdown.classList.toggle("open");
            if (pendingAlertCount > 0) {
                window.ATISAlertSound.play("warning");
            }
        });

        document.addEventListener("click", (e) => {
            if (!notifDropdown.contains(e.target)) {
                notifDropdown.classList.remove("open");
            }
        });
    }
});
