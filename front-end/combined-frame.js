// Route links back through the parent page instead of loading another HTML file.
window.navigateCombinedPage = function (page) {
    const name = page.replace(/\.html$/, "");
    window.parent.location.hash = "traditional/" + name;
};

window.getStudentPageName = function () {
    return window.parent.location.hash.slice(1).split("/")[1] || "login";
};

window.combinedPageQuery = window.parent.location.hash.split("?")[1] || "";

document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link || link.hasAttribute("data-logout")) return;
    const href = link.getAttribute("href");
    if (!href.startsWith("#") || href === "#") return;
    event.preventDefault();
    const route = href.slice(1);
    window.parent.location.hash = route.startsWith("traditional/") ? route : "student/" + route;
});
