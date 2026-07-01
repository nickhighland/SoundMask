document.addEventListener("DOMContentLoaded", () => {
  const sidebarAccordion = document.querySelector("[data-sidebar-accordion]");
  if (sidebarAccordion) {
    const mobileSidebarQuery = window.matchMedia("(max-width: 720px)");
    const syncSidebarAccordion = (query) => {
      sidebarAccordion.open = !query.matches;
      sidebarAccordion.setAttribute("data-ready", "true");
    };

    syncSidebarAccordion(mobileSidebarQuery);
    if (typeof mobileSidebarQuery.addEventListener === "function") {
      mobileSidebarQuery.addEventListener("change", syncSidebarAccordion);
    } else {
      mobileSidebarQuery.addListener(syncSidebarAccordion);
    }
  }

  document.querySelectorAll("[data-autofocus]").forEach((element) => {
    element.focus();
  });

  document.querySelectorAll("[data-log-viewer]").forEach((viewer) => {
    const endpoint = viewer.dataset.endpoint;
    const sourceSelect = viewer.querySelector("[data-log-source]");
    const linesSelect = viewer.querySelector("[data-log-lines]");
    const autoToggle = viewer.querySelector("[data-log-auto]");
    const refreshButton = viewer.querySelector("[data-log-refresh]");
    const label = viewer.querySelector("[data-log-label]");
    const path = viewer.querySelector("[data-log-path]");
    const modified = viewer.querySelector("[data-log-modified]");
    const updated = viewer.querySelector("[data-log-updated]");
    const description = viewer.querySelector("[data-log-description]");
    const content = viewer.querySelector("[data-log-content]");
    let refreshTimer = null;

    const renderPayload = (payload) => {
      label.textContent = payload.label;
      path.textContent = payload.path;
      modified.textContent = payload.modified_at || "Not available yet";
      updated.textContent = payload.updated_at;
      description.textContent = payload.description;
      content.textContent = payload.content;
    };

    const fetchLogs = async () => {
      const params = new URLSearchParams({
        source: sourceSelect.value,
        lines: linesSelect.value,
      });
      const response = await fetch(`${endpoint}?${params.toString()}`, {
        headers: {
          Accept: "application/json",
        },
      });
      if (!response.ok) {
        throw new Error(`Log refresh failed (${response.status})`);
      }
      const payload = await response.json();
      renderPayload(payload);
    };

    const updateTimer = () => {
      if (refreshTimer) {
        window.clearInterval(refreshTimer);
        refreshTimer = null;
      }
      if (autoToggle.checked) {
        refreshTimer = window.setInterval(() => {
          fetchLogs().catch(() => {});
        }, 3000);
      }
    };

    sourceSelect.addEventListener("change", () => {
      fetchLogs().catch(() => {});
    });
    linesSelect.addEventListener("change", () => {
      fetchLogs().catch(() => {});
    });
    autoToggle.addEventListener("change", updateTimer);
    refreshButton.addEventListener("click", () => {
      fetchLogs().catch(() => {});
    });

    updateTimer();
  });
});
