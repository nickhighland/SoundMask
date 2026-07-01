document.addEventListener("DOMContentLoaded", () => {
  const sidebarAccordion = document.querySelector("[data-sidebar-accordion]");
  if (sidebarAccordion) {
    const mobileSidebarQuery = window.matchMedia("(max-width: 720px)");
    let wasMobileSidebar = mobileSidebarQuery.matches;
    const syncSidebarAccordion = () => {
      const isMobileSidebar = mobileSidebarQuery.matches;
      if (isMobileSidebar) {
        if (!sidebarAccordion.hasAttribute("data-ready") || !wasMobileSidebar) {
          sidebarAccordion.open = false;
        }
      } else {
        sidebarAccordion.open = true;
      }
      sidebarAccordion.setAttribute("data-ready", "true");
      sidebarAccordion.setAttribute("data-mobile", isMobileSidebar ? "true" : "false");
      wasMobileSidebar = isMobileSidebar;
    };
    const handleSidebarViewportChange = () => {
      window.requestAnimationFrame(syncSidebarAccordion);
    };

    syncSidebarAccordion();
    if (typeof mobileSidebarQuery.addEventListener === "function") {
      mobileSidebarQuery.addEventListener("change", handleSidebarViewportChange);
    } else {
      mobileSidebarQuery.addListener(handleSidebarViewportChange);
    }
    window.addEventListener("resize", handleSidebarViewportChange);
  }

  document.querySelectorAll("[data-autofocus]").forEach((element) => {
    element.focus();
  });

  document.querySelectorAll("[data-volume-form]").forEach((form) => {
    const slider = form.querySelector("[data-volume-slider]");
    const output = form.querySelector("[data-volume-output]");
    if (!(slider instanceof HTMLInputElement) || !(output instanceof HTMLOutputElement)) {
      return;
    }

    const liveUpdates = form.dataset.volumeLive === "true";
    let submitTimer = null;
    let requestSequence = 0;

    const syncTrack = () => {
      const min = Number(slider.min || "0");
      const max = Number(slider.max || "100");
      const value = Number(slider.value || "0");
      const percent = max <= min ? 0 : ((value - min) / (max - min)) * 100;
      slider.style.setProperty(
        "--volume-fill",
        `${Math.max(0, Math.min(100, percent))}%`,
      );
    };

    const syncOutput = () => {
      output.textContent = `${slider.value}%`;
      syncTrack();
    };

    const submitVolume = async () => {
      requestSequence += 1;
      const currentRequest = requestSequence;
      const payload = new URLSearchParams({
        volume_percent: slider.value,
      });

      try {
        const response = await fetch(form.action, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
          },
          body: payload.toString(),
        });
        if (!response.ok) {
          throw new Error(`Volume update failed (${response.status})`);
        }
        const result = await response.json();
        if (currentRequest !== requestSequence) {
          return;
        }
        slider.value = String(result.volume_percent);
        syncOutput();
      } catch (_error) {
        if (currentRequest !== requestSequence) {
          return;
        }
        form.submit();
      }
    };

    const scheduleLiveSubmit = () => {
      if (!liveUpdates) {
        return;
      }
      if (submitTimer) {
        window.clearTimeout(submitTimer);
      }
      submitTimer = window.setTimeout(() => {
        submitTimer = null;
        submitVolume().catch(() => {});
      }, 120);
    };

    syncOutput();
    slider.addEventListener("input", () => {
      syncOutput();
      scheduleLiveSubmit();
    });
    slider.addEventListener("change", () => {
      if (submitTimer) {
        window.clearTimeout(submitTimer);
        submitTimer = null;
      }
      syncOutput();
      submitVolume().catch(() => {});
    });
  });

  document.querySelectorAll("[data-layer-card]").forEach((card) => {
    const toggle = card.querySelector("[data-layer-toggle]");
    const slider = card.querySelector("[data-layer-slider]");
    const output = card.querySelector("[data-layer-output]");
    if (
      !(toggle instanceof HTMLInputElement)
      || !(slider instanceof HTMLInputElement)
      || !(output instanceof HTMLOutputElement)
    ) {
      return;
    }

    const syncLayerTrack = () => {
      const min = Number(slider.min || "0");
      const max = Number(slider.max || "100");
      const value = Number(slider.value || "0");
      const percent = max <= min ? 0 : ((value - min) / (max - min)) * 100;
      slider.style.setProperty(
        "--layer-fill",
        `${Math.max(0, Math.min(100, percent))}%`,
      );
    };

    const syncLayerCard = () => {
      slider.disabled = !toggle.checked;
      output.textContent = `${slider.value}%`;
      syncLayerTrack();
      card.classList.toggle("is-selected", toggle.checked);
    };

    toggle.addEventListener("change", syncLayerCard);
    slider.addEventListener("input", syncLayerCard);
    syncLayerCard();
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
