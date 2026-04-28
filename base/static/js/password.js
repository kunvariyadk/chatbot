// ─── SVG icons ───────────────────────────────────────────────
const EYE_OPEN = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
  <circle cx="12" cy="12" r="3"/>
</svg>`;

const EYE_OFF = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
  <line x1="1" y1="1" x2="23" y2="23"/>
</svg>`;

document.addEventListener('DOMContentLoaded', function () {

    // ─── Eye toggle ──────────────────────────────────────────────────────────
    // Use event delegation + closest() so clicks on the SVG/path INSIDE the
    // button are still handled correctly (e.target is often the child <svg>).
    document.addEventListener('click', function (e) {
        const btn = e.target.closest('.toggle-password');
        if (!btn) return;
        const input = document.getElementById(btn.getAttribute('data-target'));
        if (!input) return;
        const isHidden = input.type === 'password';
        input.type    = isHidden ? 'text' : 'password';
        btn.innerHTML = isHidden ? EYE_OFF : EYE_OPEN;
    });

    // ─── Change-password form: new vs confirm must match ────────────────────
    const passwordForm = document.getElementById('passwordForm');
    if (passwordForm) {
        passwordForm.addEventListener('submit', function (e) {
            const np = document.getElementById('new_password').value;
            const cp = document.getElementById('confirm_password').value;
            if (np !== cp) {
                e.preventDefault();
                alert('Passwords do not match!');
            }
        });
    }

    // ─── Reset-password form: password vs confirm must match ────────────────
    const resetPasswordForm = document.getElementById('resetPasswordForm');
    if (resetPasswordForm) {
        resetPasswordForm.addEventListener('submit', function (e) {
            const pw = document.getElementById('password').value;
            const cp = document.getElementById('confirm_password').value;
            if (pw !== cp) {
                e.preventDefault();
                alert('Passwords do not match!');
            }
        });
    }

    // ─── Sidebar menus ───────────────────────────────────────────────────────
    const botsMenu = document.getElementById('botsMenu');
    const botsSubmenu = document.getElementById('botsSubmenu');
    const accountMenu = document.getElementById('accountMenu');
    const accountSubmenu = document.getElementById('accountSubmenu');

    if (botsMenu && botsSubmenu) {
        botsMenu.addEventListener('click', function (e) {
            e.preventDefault();
            if (accountSubmenu && accountSubmenu.classList.contains('open')) {
                accountSubmenu.classList.remove('open');
                accountMenu.classList.remove('expanded');
            }
            this.classList.toggle('expanded');
            botsSubmenu.classList.toggle('open');
        });
    }

    if (accountMenu && accountSubmenu) {
        accountMenu.addEventListener('click', function (e) {
            e.preventDefault();
            if (botsSubmenu && botsSubmenu.classList.contains('open')) {
                botsSubmenu.classList.remove('open');
                botsMenu.classList.remove('expanded');
            }
            this.classList.toggle('expanded');
            accountSubmenu.classList.toggle('open');
        });
    }

    // Close submenus when clicking outside
    document.addEventListener('click', function (e) {
        if (botsMenu && botsSubmenu && !e.target.closest('#botsMenu') && !e.target.closest('#botsSubmenu')) {
            botsSubmenu.classList.remove('open');
            botsMenu.classList.remove('expanded');
        }
        if (accountMenu && accountSubmenu && !e.target.closest('#accountMenu') && !e.target.closest('#accountSubmenu')) {
            accountSubmenu.classList.remove('open');
            accountMenu.classList.remove('expanded');
        }
    });

    // ─── Mobile sidebar toggle ───────────────────────────────────────────────
    const mobileMenuToggle = document.getElementById('mobileMenuToggle');
    const sidebar          = document.getElementById('sidebar');

    if (mobileMenuToggle && sidebar) {
        mobileMenuToggle.addEventListener('click', function () {
            sidebar.classList.toggle('open');
        });

        document.addEventListener('click', function (e) {
            if (window.innerWidth <= 968) {
                if (!sidebar.contains(e.target) && !mobileMenuToggle.contains(e.target)) {
                    sidebar.classList.remove('open');
                }
            }
        });
    }
});