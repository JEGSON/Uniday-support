// URL fragments are not sent to the server in the initial GET or access logs.
const fragment = new URLSearchParams(window.location.hash.slice(1));
const tokenField = document.getElementById('verification-token');
const submit = document.getElementById('verify-submit');
const status = document.getElementById('token-status');
const token = fragment.get('token') || (tokenField && tokenField.value);
if (tokenField && submit && status && /^[A-Za-z0-9_-]{43}$/.test(token || '')) {
  tokenField.value = token;
  submit.disabled = false;
  window.history.replaceState(null, '', window.location.pathname);
} else if (status) {
  status.hidden = false;
}
