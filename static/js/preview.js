document.addEventListener("DOMContentLoaded", () => {
  // Auto-clear the “Saved” message after 2s
  const status = document.querySelector(".status");
  if (status) {
    setTimeout(() => { status.textContent = ""; }, 2000);
  }
  // Focus the textarea when editing
  const textarea = document.querySelector("textarea");
  if (textarea) textarea.focus();
});
