// The main app and both alternate layouts share the templates in index.html.
const mainFrontend = document.querySelector("#combinedMain");
const alternateFrontend = document.querySelector("#combinedFrame");
let loadedFrontend = "";

function showCombinedFrontend() {
    const route = window.location.hash.slice(1).split("?")[0];
    let [frontend, page] = route.split("/");
    if (!["main", "traditional", "student"].includes(frontend)) frontend = "main";
    page = page || (frontend === "student" ? "login" : "index");

    let template = null;
    if (frontend !== "main") {
        template = document.getElementById(
            `combined-${frontend}-${frontend === "student" ? "index" : page}`,
        );
        if (
            !template ||
            (frontend === "student" &&
                !["login", "dashboard", "profile", "progress", "lactation"].includes(page))
        ) {
            window.location.replace("#main");
            return;
        }
    }

    mainFrontend.hidden = frontend !== "main";
    alternateFrontend.hidden = frontend === "main";
    document.querySelectorAll("[data-frontend]").forEach((link) => {
        if (link.dataset.frontend === frontend) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
    });
    if (frontend === "main") {
        document.title = "NutriCare | Nutrition & Dietitian Portal";
        return;
    }

    // Keep the student form values when navigating between its sections.
    if (frontend === "student" && loadedFrontend === "student") {
        alternateFrontend.contentWindow.showStudentPage?.();
        return;
    }

    loadedFrontend = frontend;
    alternateFrontend.title = template.dataset.title;
    document.title = template.dataset.title;
    const scripts =
        frontend === "traditional"
            ? '<script src="/static/support.js?v=2" defer></script><script src="/static/traditional/traditional.js?v=2" defer></script>'
            : '<script src="/static/student/student.js?v=2" defer></script>';
    alternateFrontend.srcdoc = `<!doctype html><html lang="en"><head>
    <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="/static/${frontend}/${frontend}.css">
    <script src="/static/combined-frame.js?v=1" defer></script>${scripts}
    </head><body>${template.innerHTML}</body></html>`;
}

window.addEventListener("hashchange", showCombinedFrontend);
showCombinedFrontend();
