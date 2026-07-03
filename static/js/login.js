(function () {
    "use strict";

    var toggleBtn = document.getElementById("toggle-password");
    var passwordInput = document.getElementById("password");
    var form = document.getElementById("login-form");
    var signInBtn = document.getElementById("signin-btn");

    if (toggleBtn && passwordInput) {
        toggleBtn.addEventListener("click", function () {
            passwordInput.type = passwordInput.type === "password" ? "text" : "password";
        });
    }
    if (form && signInBtn) {
        form.addEventListener("submit", function () {
            signInBtn.classList.add("is-loading");
        });
    }
})();
