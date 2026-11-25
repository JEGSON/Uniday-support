// The server enforces the 15-minute idle timeout; this is only a gentle hint.
// Activity in another tab may have extended the session, so the wording is approximate.
const sessionWarning = document.getElementById('session-warning');
if (sessionWarning) {
  window.setTimeout(() => { sessionWarning.hidden = false; }, 13 * 60 * 1000);
}
