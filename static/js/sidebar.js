/**
 * sidebar.js — Shared sidebar behaviour: collapse toggle + drag-to-resize.
 */
document.addEventListener("DOMContentLoaded", () => {
    const sidebar = document.getElementById("sidebar");
    const collapseBtn = document.getElementById("sidebar-collapse");
    if (!sidebar) return;

    /* ---------- Collapse ---------- */
    if (collapseBtn) {
        collapseBtn.addEventListener("click", () => {
            document.body.classList.toggle("sidebar-collapsed");
            // Reset any custom drag width when collapsing
            if (document.body.classList.contains("sidebar-collapsed")) {
                sidebar.style.width = "";
                document.querySelector(".main-area").style.marginLeft = "";
            }
        });
    }

    /* ---------- Drag-to-resize ---------- */
    const DRAG_HANDLE_WIDTH = 6;          // px – invisible hit area on sidebar right edge
    const MIN_WIDTH = 140;
    const MAX_WIDTH = 400;
    let isDragging = false;
    let startX = 0;
    let startWidth = 0;

    // Change cursor when hovering near right edge
    sidebar.addEventListener("mousemove", (e) => {
        if (isDragging) return;
        const rect = sidebar.getBoundingClientRect();
        if (rect.right - e.clientX <= DRAG_HANDLE_WIDTH) {
            sidebar.style.cursor = "col-resize";
        } else {
            sidebar.style.cursor = "";
        }
    });

    sidebar.addEventListener("mouseleave", () => {
        if (!isDragging) sidebar.style.cursor = "";
    });

    // Start drag
    sidebar.addEventListener("mousedown", (e) => {
        const rect = sidebar.getBoundingClientRect();
        if (rect.right - e.clientX > DRAG_HANDLE_WIDTH) return;
        if (document.body.classList.contains("sidebar-collapsed")) return;

        isDragging = true;
        startX = e.clientX;
        startWidth = rect.width;

        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
        e.preventDefault();
    });

    // During drag
    document.addEventListener("mousemove", (e) => {
        if (!isDragging) return;

        const delta = e.clientX - startX;
        let newWidth = Math.round(startWidth + delta);
        newWidth = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, newWidth));

        sidebar.style.width = newWidth + "px";
        document.querySelector(".main-area").style.marginLeft = newWidth + "px";
    });

    // End drag
    document.addEventListener("mouseup", () => {
        if (!isDragging) return;
        isDragging = false;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        sidebar.style.cursor = "";
    });
});
