document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-password-toggle]").forEach((button) => {
        const passwordId = button.getAttribute("aria-controls");
        const password = passwordId ? document.getElementById(passwordId) : null;

        if (!(password instanceof HTMLInputElement)) {
            return;
        }

        button.addEventListener("click", () => {
            const showPassword = password.type === "password";
            password.type = showPassword ? "text" : "password";
            button.textContent = showPassword ? "Hide" : "Show";
            button.setAttribute(
                "aria-label",
                showPassword ? "Hide password" : "Show password"
            );
            button.setAttribute("aria-pressed", String(showPassword));
        });
    });
});
