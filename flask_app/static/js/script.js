
document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('theme-toggle');
    const htmlTag = document.documentElement;

    // 1. Determine the starting theme
    const getStoredTheme = () => localStorage.getItem('theme');
    const getSystemTheme = () => window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';

    // Set initial theme
    const initialTheme = getStoredTheme() || getSystemTheme();
    htmlTag.setAttribute('data-theme', initialTheme);

    // 2. Toggle Event Listener
    if (themeToggle) {
        themeToggle.addEventListener('click', (e) => {
            e.preventDefault();

            // Get current state
            const currentTheme = htmlTag.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

            // Apply to HTML tag
            htmlTag.setAttribute('data-theme', newTheme);

            // Persist in localStorage
            localStorage.setItem('theme', newTheme);

            document.cookie = `theme=${newTheme}; path=/; max-age=31536000; SameSite=Lax`;

            // Optional: Log for debugging
            console.log(`Theme switched to: ${newTheme}`);
        });
    }
});

function togglePassword(inputId, container) {
    const passwordInput = document.getElementById(inputId);
    const eyeOpen = container.querySelector('#eye-open');
    const eyeClosed = container.querySelector('#eye-closed');

    if (passwordInput.type === "password") {
        passwordInput.type = "text";
        passwordInput.placeholder = "";
        eyeOpen.setAttribute("display", "none");
        eyeClosed.removeAttribute("display");
    } else {
        passwordInput.type = "password";
        passwordInput.placeholder = "••••••••";
        eyeOpen.removeAttribute("display");
        eyeClosed.setAttribute("display", "none");
    }
};


document.addEventListener('DOMContentLoaded', () => {
    // Seleccionamos todos los mensajes flash
    const flashes = document.querySelectorAll('.flash-message');

    flashes.forEach(flash => {
        // 1. Tiempo de espera antes de empezar a desaparecer (ej: 4 segundos)
        setTimeout(() => {
            flash.classList.add('flash-fade-out');

            // 2. Esperar a que la transición de CSS termine para borrarlo del DOM
            flash.addEventListener('animationend', () => {
                flash.remove();
            });
        }, 4000);
    });
});
