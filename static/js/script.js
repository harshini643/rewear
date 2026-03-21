function validateSignup() {
    let name = document.getElementById("signupName").value.trim();
    let email = document.getElementById("signupEmail").value.trim();
    let password = document.getElementById("signupPassword").value.trim();
    let error = document.getElementById("signupError");

    error.innerHTML = "";

    if (name === "" || email === "" || password === "") {
        error.innerHTML = "All fields are required.";
        return false;
    }

    if (password.length < 6) {
        error.innerHTML = "Password must be at least 6 characters.";
        return false;
    }

    return true;
}

function validateLogin() {
    let email = document.getElementById("loginEmail").value.trim();
    let password = document.getElementById("loginPassword").value.trim();
    let error = document.getElementById("loginError");

    error.innerHTML = "";

    if (email === "" || password === "") {
        error.innerHTML = "Both fields are required.";
        return false;
    }

    return true;
}