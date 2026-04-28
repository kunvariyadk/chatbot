document.addEventListener('DOMContentLoaded', function() {
    const registerForm = document.getElementById('registerForm');
    const usernameInput = document.getElementById('User_name');
    const emailInput = document.getElementById('email');
    const phoneInput = document.getElementById('phone');
    const passwordInput = document.getElementById('password');
    const confirmPasswordInput = document.getElementById('confirm_password');
    const termsCheckbox = document.getElementById('terms');
    const togglePassword = document.getElementById('togglePassword');
    const toggleConfirmPassword = document.getElementById('toggleConfirmPassword');

    // --- Phone Number Logic (10 digits only, no +91 in value) ---
    phoneInput.addEventListener('input', function(e) {
        let num = this.value.replace(/\D/g, '');
        if (num.length > 10) {
            num = num.slice(0, 10);
        }
        this.value = num;
    });

    // --- NEW: Password Strength Helper ---
    function isStrongPassword(password) {
        // Requirements: 8+ chars, 1 Uppercase, 1 Number, 1 Special Char (@$!%*?&)
        const strongRegex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/;
        return strongRegex.test(password);
    }

    // Password toggle for main password
    togglePassword.addEventListener('click', function() {
        const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
        passwordInput.setAttribute('type', type);
        if (type === 'password') {
            this.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>';
        } else {
            this.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>';
        }
    });

    // Password toggle for confirm password
    toggleConfirmPassword.addEventListener('click', function() {
        const type = confirmPasswordInput.getAttribute('type') === 'password' ? 'text' : 'password';
        confirmPasswordInput.setAttribute('type', type);
        if (type === 'password') {
            this.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>';
        } else {
            this.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>';
        }
    });

    // Form validation
    registerForm.addEventListener('submit', function(e) {
        let isValid = true;

        if (usernameInput.value.length < 3) {
            showError(usernameInput, 'Username must be at least 3 characters');
            isValid = false;
        } else {
            clearError(usernameInput);
        }

        if (!validateEmail(emailInput.value)) {
            showError(emailInput, 'Please enter a valid email address');
            isValid = false;
        } else {
            clearError(emailInput);
        }

        if (phoneInput.value.length !== 10) {
            showError(phoneInput, 'Phone number must be exactly 10 digits');
            isValid = false;
        } else {
            clearError(phoneInput);
        }

        // --- UPGRADED PASSWORD VALIDATION ---
        if (!isStrongPassword(passwordInput.value)) {
            showError(passwordInput, 'Must be 8+ chars with uppercase, number & symbol (@$!%*?&)');
            isValid = false;
        } else {
            clearError(passwordInput);
        }

        if (passwordInput.value !== confirmPasswordInput.value) {
            showError(confirmPasswordInput, 'Passwords do not match');
            isValid = false;
        } else {
            clearError(confirmPasswordInput);
        }

        if (!termsCheckbox.checked) {
            alert('Please agree to the Terms of Service and Privacy Policy');
            isValid = false;
        }

        if (!isValid) {
            e.preventDefault();
        }
    });

    // Real-time validation
    usernameInput.addEventListener('blur', function() {
        if (this.value.length > 0 && this.value.length < 3) {
            showError(this, 'Username must be at least 3 characters');
        } else {
            clearError(this);
        }
    });

    emailInput.addEventListener('blur', function() {
        if (this.value.length > 0 && !validateEmail(this.value)) {
            showError(this, 'Please enter a valid email address with @ or .');
        } else {
            clearError(this);
        }
    });

    confirmPasswordInput.addEventListener('input', function() {
        if (this.value.length > 0 && passwordInput.value !== this.value) {
            showError(this, 'Passwords do not match');
        } else {
            clearError(this);
        }
    });

    function validateEmail(email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    }

    function showError(input, message) {
        clearError(input);

        if (input.id === 'phone') {
            input.parentElement.style.borderColor = '#f56565';
        } else {
            input.style.borderColor = '#f56565';
        }

        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = message;

        if (input.id === 'phone') {
            input.parentElement.after(errorDiv);
        } else if (input.type === 'password') {
            input.parentElement.after(errorDiv);
        } else {
            input.after(errorDiv);
        }
    }

    function clearError(input) {
        if (input.id === 'phone') {
            input.parentElement.style.borderColor = '#e2e8f0';
        } else {
            input.style.borderColor = '#e2e8f0';
        }

        let errorDiv;
        if (input.id === 'phone' || input.type === 'password') {
            errorDiv = input.parentElement.nextElementSibling;
        } else {
            errorDiv = input.nextElementSibling;
        }

        if (errorDiv && errorDiv.classList.contains('error-message')) {
            errorDiv.remove();
        }
    }

    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });
});