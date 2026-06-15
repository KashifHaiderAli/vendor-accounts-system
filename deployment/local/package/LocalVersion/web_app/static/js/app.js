document.addEventListener("DOMContentLoaded", () => {
    document.body.classList.add("app-ready");

    const sidebarToggle = document.querySelector(".sidebar-mobile-toggle");
    const sidebar = document.querySelector(".app-sidebar");
    const sidebarScrollKey = "vendor_sidebar_scroll_top";

    if (sidebar) {
        const savedSidebarTop = sessionStorage.getItem(sidebarScrollKey);
        if (savedSidebarTop !== null) {
            sidebar.scrollTop = Number.parseInt(savedSidebarTop, 10) || 0;
        }

        sidebar.addEventListener("scroll", () => {
            sessionStorage.setItem(sidebarScrollKey, String(sidebar.scrollTop));
        }, {passive: true});

        window.addEventListener("beforeunload", () => {
            sessionStorage.setItem(sidebarScrollKey, String(sidebar.scrollTop));
        });
    }

    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener("click", () => {
            document.body.classList.toggle("sidebar-open");
        });

        sidebar.addEventListener("click", (event) => {
            const link = event.target.closest("a");
            if (link && window.matchMedia("(max-width: 900px)").matches) {
                document.body.classList.remove("sidebar-open");
            }
        });
    }
});
