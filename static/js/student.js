// The counter is an aid only; the server enforces the length limit as well.
const description = document.getElementById('description');
const count = document.getElementById('description-count');
if (description && count) {
  const updateCount = () => { count.textContent = `${description.value.length.toLocaleString()} of 3,000 characters`; };
  description.addEventListener('input', updateCount);
  updateCount();
}
