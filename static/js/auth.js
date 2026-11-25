/* Password visibility is optional: fields stay usable without JavaScript. */
document.querySelectorAll('[data-password-toggle]').forEach((button) => {
  const input = document.getElementById(button.getAttribute('aria-controls'));
  if (!input || input.type !== 'password') return;

  button.hidden = false;
  button.addEventListener('click', () => {
    const isVisible = input.type === 'text';
    input.type = isVisible ? 'password' : 'text';
    button.textContent = isVisible ? 'Show password' : 'Hide password';
    button.setAttribute('aria-pressed', String(!isVisible));
  });
});

/* This is a length reminder, not a strength score. The server must apply the
   complete password policy, including checks for common or compromised values. */
const password = document.querySelector('input[autocomplete="new-password"]#password');
const feedback = document.getElementById('password-feedback');

if (password && feedback) {
  let feedbackTimer;
  password.addEventListener('input', () => {
    window.clearTimeout(feedbackTimer);
    // A short debounce avoids announcing a message on every keystroke.
    feedbackTimer = window.setTimeout(() => {
      // Match the browser's minlength/maxlength measurement (UTF-16 units).
      const length = password.value.length;
      if (length === 0) {
        feedback.textContent = '';
      } else if (length < 15) {
        feedback.textContent = 'Keep going: use at least 15 characters.';
      } else if (length > 128) {
        feedback.textContent = 'Use no more than 128 characters.';
      } else {
        feedback.textContent = 'The length looks good. Choose a password you do not use elsewhere.';
      }
    }, 500);
  });
}
