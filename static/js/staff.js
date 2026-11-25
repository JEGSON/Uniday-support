// Native modal dialogs provide focus containment and Escape-to-close.
document.querySelectorAll('[data-open-dialog]').forEach((trigger) => {
  const dialog = document.getElementById(trigger.dataset.openDialog);
  if (!dialog || typeof dialog.showModal !== 'function') return;
  trigger.hidden = false;
  trigger.addEventListener('click', () => {
    dialog.showModal();
    dialog.querySelector('[data-close-dialog]')?.focus();
  });
  dialog.querySelector('[data-close-dialog]')?.addEventListener('click', () => dialog.close());
  dialog.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      dialog.close();
    }
  });
  dialog.addEventListener('close', () => trigger.focus());
});
