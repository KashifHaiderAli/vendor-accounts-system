document.addEventListener("DOMContentLoaded", () => {
    document.body.classList.add("app-ready");

    const sidebarToggle = document.querySelector(".sidebar-mobile-toggle");
    const sidebar = document.querySelector(".app-sidebar");

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
