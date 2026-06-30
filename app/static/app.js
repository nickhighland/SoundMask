document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-autofocus]").forEach((element) => {
    element.focus();
  });
});