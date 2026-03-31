/* =============================================
   TOAST SYSTEM  — defined first so the Jinja
   <script> block at bottom of HTML can call it
   ============================================= */

const toastIcons = {
    success: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
    error:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
    warning: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    info:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`
};

// Toast titles matching your Flask flash categories
const toastTitles = {
    success: 'Success',
    error:   'Error',
    warning: 'Warning',
    info:    'Notice'
};

function showToast(type, title, msg, duration) {
    duration = duration || 4000;
    var container = document.getElementById('toastContainer');
    if (!container) return;

    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.innerHTML =
        '<div class="toast-icon-wrap">' + (toastIcons[type] || toastIcons.info) + '</div>' +
        '<div class="toast-body">' +
            '<p class="toast-title">' + (title || toastTitles[type] || 'Notice') + '</p>' +
            '<p class="toast-msg">' + msg + '</p>' +
        '</div>' +
        '<button class="toast-close" aria-label="Close">&#x2715;</button>' +
        '<div class="toast-progress" style="animation-duration:' + duration + 'ms;"></div>';

    toast.querySelector('.toast-close').addEventListener('click', function () {
        removeToast(toast);
    });

    container.appendChild(toast);

    // Slight delay so browser registers the element before animating
    setTimeout(function () { toast.classList.add('show'); }, 20);

    toast._timer = setTimeout(function () { removeToast(toast); }, duration);
}

function removeToast(toast) {
    if (!toast || toast.classList.contains('hide')) return;
    clearTimeout(toast._timer);
    toast.classList.remove('show');
    toast.classList.add('hide');
    setTimeout(function () { if (toast.parentElement) toast.remove(); }, 420);
}


/* =============================================
   EVERYTHING BELOW NEEDS THE DOM READY
   ============================================= */

document.addEventListener('DOMContentLoaded', function () {

    var loginForm      = document.getElementById('loginForm');
    var emailInput     = document.getElementById('email');
    var passwordInput  = document.getElementById('password');
    var togglePassword = document.getElementById('togglePassword');


    /* =============================================
       PASSWORD TOGGLE
       ============================================= */

    if (togglePassword) {
        togglePassword.addEventListener('click', function () {
            var type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
            passwordInput.setAttribute('type', type);
            this.innerHTML = type === 'password'
                ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>'
                : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>';
        });
    }


    /* =============================================
       FIELD HELPERS
       ============================================= */

    function validateEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }

    function showFieldError(input, message) {
        clearFieldError(input);
        input.style.borderColor = '#f56565';
        var div = document.createElement('div');
        div.className = 'error-message';
        div.textContent = message;
        input.parentElement.appendChild(div);
    }

    function clearFieldError(input) {
        input.style.borderColor = '#e2e8f0';
        var existing = input.parentElement.querySelector('.error-message');
        if (existing) existing.remove();
    }

    if (emailInput) {
        emailInput.addEventListener('blur', function () {
            if (this.value && !validateEmail(this.value)) {
                showFieldError(this, 'Please enter a valid email address');
            } else {
                clearFieldError(this);
            }
        });
    }

    if (passwordInput) {
        passwordInput.addEventListener('input', function () {
            if (this.value.length > 0 && this.value.length < 6) {
                showFieldError(this, 'Password must be at least 6 characters');
            } else {
                clearFieldError(this);
            }
        });
    }


    /* =============================================
       FORM SUBMIT
       Client-side check → toast → if valid, POST
       to Flask. Flask then flashes its own message
       which renders as a toast on next page load.
       ============================================= */

    if (loginForm) {
        loginForm.addEventListener('submit', function (e) {
            // Always stop reload first so toasts are visible
            e.preventDefault();

            var email    = emailInput.value.trim();
            var password = passwordInput.value;

            clearFieldError(emailInput);
            clearFieldError(passwordInput);

            // Collect errors
            var emailError    = '';
            var passwordError = '';

            if (!email) {
                emailError = 'Please enter your email address.';
            } else if (!validateEmail(email)) {
                emailError = 'Please enter a valid email address.';
            }

            if (!password) {
                passwordError = 'Please enter your password.';
            } else if (password.length < 6) {
                passwordError = 'Password must be at least 6 characters.';
            }

            // If any error — show toasts and STOP
            if (emailError || passwordError) {
                if (emailError) {
                    showFieldError(emailInput, emailError);
                    showToast('error', 'Invalid Email', emailError);
                }
                if (passwordError) {
                    showFieldError(passwordInput, passwordError);
                    showToast('warning', 'Invalid Password', passwordError);
                }
                return; // hard stop — success block never reached
            }

            // Both fields valid — submit to Flask
            // Flask will flash 'Invalid email or password.' or 'Welcome back, Name!'
            // Those flash messages render as toasts via the Jinja block in login.html
            loginForm.submit();
        });
    }

});