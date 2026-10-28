const studentPages = document.querySelectorAll("[data-student-page]");
const studentLinks = document.querySelectorAll("[data-student-link]");
const studentLogin = document.querySelector("#studentLogin");
const studentWorkspace = document.querySelector("#studentWorkspace");

// Each hash points to a section in index.html, so Back and Forward still work.
function showStudentPage() {
    let pageName = window.getStudentPageName
        ? window.getStudentPageName()
        : window.location.hash.slice(1) || "login";
    const pageNames = ["login", "dashboard", "profile", "progress", "lactation"];

    if (!pageNames.includes(pageName)) {
        pageName = "login";
    }

    studentLogin.hidden = pageName !== "login";
    studentWorkspace.hidden = pageName === "login";

    studentPages.forEach((page) => {
        page.hidden = page.dataset.studentPage !== pageName;
    });

    studentLinks.forEach((link) => {
        const isActive = link.dataset.studentLink === pageName;
        link.classList.toggle("active", isActive);
        if (isActive) {
            link.setAttribute("aria-current", "page");
        } else {
            link.removeAttribute("aria-current");
        }
    });

    const currentPage = document.querySelector(`[data-student-page="${pageName}"]`);
    const heading = currentPage.querySelector("h1");
    document.title =
        "Student Dietitian App - " + (pageName === "login" ? "Login" : heading.textContent);
    if (window.parent !== window) window.parent.document.title = document.title;
    if (pageName !== "login") {
        heading.setAttribute("tabindex", "-1");
        heading.focus();
    }
}

window.addEventListener("hashchange", showStudentPage);
showStudentPage();

document.querySelectorAll("[data-student-message]").forEach((element) => {
    const showMessage = (event) => {
        event.preventDefault();
        const message = element.closest("form, section, div")?.querySelector(".student-message");
        if (message) message.textContent = "Your information was saved for this student project.";
    };
    element.addEventListener(element.tagName === "FORM" ? "submit" : "click", showMessage);
});
