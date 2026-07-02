document.addEventListener("DOMContentLoaded", () => {
  const sidebarAccordion = document.querySelector("[data-sidebar-accordion]");
  if (sidebarAccordion) {
    const compactSidebarQuery = window.matchMedia("(max-width: 1080px)");
    let wasCompactSidebar = compactSidebarQuery.matches;
    const syncSidebarAccordion = () => {
      const isCompactSidebar = compactSidebarQuery.matches;
      if (isCompactSidebar) {
        if (!sidebarAccordion.hasAttribute("data-ready") || !wasCompactSidebar) {
          sidebarAccordion.open = false;
        }
      } else {
        sidebarAccordion.open = true;
      }
      sidebarAccordion.setAttribute("data-ready", "true");
      sidebarAccordion.setAttribute("data-mobile", isCompactSidebar ? "true" : "false");
      wasCompactSidebar = isCompactSidebar;
    };
    const handleSidebarViewportChange = () => {
      window.requestAnimationFrame(syncSidebarAccordion);
    };

    syncSidebarAccordion();
    if (typeof compactSidebarQuery.addEventListener === "function") {
      compactSidebarQuery.addEventListener("change", handleSidebarViewportChange);
    } else {
      compactSidebarQuery.addListener(handleSidebarViewportChange);
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
    const preview = card.querySelector("[data-layer-preview]");
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    if (
      !(toggle instanceof HTMLInputElement)
      || !(slider instanceof HTMLInputElement)
      || !(output instanceof HTMLElement)
      || !(preview instanceof HTMLMediaElement)
    ) {
      return;
    }

    let previewAudioContext = null;
    let previewGainNode = null;

    const normalizedSliderValue = () => Math.max(
      0,
      Math.min(1, Number(slider.value || "0") / 100),
    );

    const ensurePreviewAudioGraph = async () => {
      if (!AudioContextCtor) {
        return false;
      }
      if (previewGainNode && previewAudioContext) {
        if (previewAudioContext.state === "suspended") {
          try {
            await previewAudioContext.resume();
          } catch (_error) {
            return false;
          }
        }
        return true;
      }
      try {
        previewAudioContext = previewAudioContext || new AudioContextCtor();
        const sourceNode = previewAudioContext.createMediaElementSource(preview);
        previewGainNode = previewAudioContext.createGain();
        sourceNode.connect(previewGainNode);
        previewGainNode.connect(previewAudioContext.destination);
        if (previewAudioContext.state === "suspended") {
          await previewAudioContext.resume();
        }
        return true;
      } catch (_error) {
        previewAudioContext = null;
        previewGainNode = null;
        return false;
      }
    };

    const syncPreviewVolume = () => {
      const volume = normalizedSliderValue();
      if (previewGainNode && previewAudioContext) {
        preview.volume = 1;
        previewGainNode.gain.setValueAtTime(
          volume,
          previewAudioContext.currentTime,
        );
        return;
      }
      preview.volume = volume;
    };

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
      output.textContent = `${slider.value}%`;
      syncLayerTrack();
      syncPreviewVolume();
      card.classList.toggle("is-selected", toggle.checked);
    };

    toggle.addEventListener("change", syncLayerCard);
    slider.addEventListener("input", syncLayerCard);
    slider.addEventListener("change", syncLayerCard);
    preview.addEventListener("play", () => {
      ensurePreviewAudioGraph()
        .then(() => {
          syncPreviewVolume();
        })
        .catch(() => {
          syncPreviewVolume();
        });
    });
    preview.addEventListener("loadedmetadata", syncLayerCard);
    syncLayerCard();
  });

  document.querySelectorAll("[data-builder-preview-button]").forEach((button) => {
    const form = document.querySelector("#sound-mix-form");
    const player = document.querySelector("[data-builder-preview-player]");
    const status = document.querySelector("[data-builder-preview-status]");
    if (
      !(button instanceof HTMLButtonElement)
      || !(form instanceof HTMLFormElement)
      || !(player instanceof HTMLAudioElement)
      || !(status instanceof HTMLElement)
    ) {
      return;
    }

    let objectUrl = null;

    button.addEventListener("click", async () => {
      button.disabled = true;
      status.textContent = "Preparing browser preview...";
      try {
        const formData = new FormData(form);
        const response = await fetch("/sounds/preview-builder", {
          method: "POST",
          body: new URLSearchParams(formData),
          headers: {
            Accept: "audio/wav,audio/flac,text/plain",
          },
        });
        if (!response.ok) {
          const detail = await response.text();
          throw new Error(detail || `Preview build failed (${response.status})`);
        }
        const blob = await response.blob();
        if (objectUrl) {
          URL.revokeObjectURL(objectUrl);
        }
        objectUrl = URL.createObjectURL(blob);
        player.src = objectUrl;
        player.dataset.ready = "true";
        await player.play();
        status.textContent = "Browser preview is playing. This does not interrupt the appliance output.";
      } catch (error) {
        status.textContent = error instanceof Error
          ? error.message
          : "Browser preview could not be prepared.";
      } finally {
        button.disabled = false;
      }
    });
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

  document.querySelectorAll("[data-update-monitor]").forEach((monitor) => {
    const endpoint = monitor.dataset.statusEndpoint;
    const monitorEnabled = monitor.dataset.monitorEnabled === "true";
    if (!endpoint || !monitorEnabled) {
      return;
    }

    const badge = monitor.querySelector("[data-update-badge]");
    const summary = document.querySelector("[data-update-summary]");
    const heading = document.querySelector("[data-update-monitor-heading]");
    const message = document.querySelector("[data-update-monitor-message]");
    const baselineVersion = monitor.dataset.currentVersion || "";
    const baselineCommit = monitor.dataset.currentCommit || "";
    const baselineLastInstall = monitor.dataset.lastInstallAt || "";
    let pollTimer = null;

    const setBadge = (state, text) => {
      if (!(badge instanceof HTMLElement)) {
        return;
      }
      badge.classList.remove("ok", "warning", "pending", "error");
      badge.classList.add(state);
      badge.textContent = text;
    };

    const renderUpdateState = (status) => {
      if (summary instanceof HTMLElement) {
        summary.textContent = status.status_message || "Checking update status...";
      }
      if (status.last_error) {
        if (heading instanceof HTMLElement) {
          heading.textContent = "Update issue";
        }
        if (message instanceof HTMLElement) {
          message.textContent = status.last_error;
        }
        setBadge("error", "Attention needed");
        return;
      }
      if (status.install_in_progress) {
        if (heading instanceof HTMLElement) {
          heading.textContent = "Installing update";
        }
        if (message instanceof HTMLElement) {
          message.textContent = "SoundMask is installing the update now. This page will refresh automatically after the service comes back online.";
        }
        setBadge("pending", "Installing update");
        return;
      }
      if (status.install_requested) {
        if (heading instanceof HTMLElement) {
          heading.textContent = "Update install requested";
        }
        if (message instanceof HTMLElement) {
          message.textContent = "SoundMask will install the update and restart itself shortly. This page will refresh automatically when the new version is live.";
        }
        setBadge("pending", "Install queued");
        return;
      }
      if (status.update_available) {
        setBadge("warning", "Update available");
        return;
      }
      setBadge("ok", "Up to date");
    };

    const installCompleted = (status) => {
      if (status.install_requested || status.install_in_progress || status.last_error) {
        return false;
      }
      return Boolean(
        (status.last_install_at && status.last_install_at !== baselineLastInstall)
        || (baselineCommit && status.current_commit && status.current_commit !== baselineCommit)
        || (baselineVersion && status.current_version && status.current_version !== baselineVersion)
        || status.status_message === "Update installed successfully.",
      );
    };

    const schedulePoll = (delayMs) => {
      if (pollTimer) {
        window.clearTimeout(pollTimer);
      }
      pollTimer = window.setTimeout(() => {
        pollUpdateStatus().catch(() => {});
      }, delayMs);
    };

    const pollUpdateStatus = async () => {
      try {
        const response = await fetch(endpoint, {
          headers: {
            Accept: "application/json",
          },
        });
        if (!response.ok) {
          throw new Error(`Update status refresh failed (${response.status})`);
        }
        const status = await response.json();
        renderUpdateState(status);
        if (installCompleted(status)) {
          if (message instanceof HTMLElement) {
            message.textContent = "Update installed successfully. Refreshing this page now.";
          }
          window.location.reload();
          return;
        }
        schedulePoll(3000);
      } catch (_error) {
        if (heading instanceof HTMLElement) {
          heading.textContent = "Installing update";
        }
        if (message instanceof HTMLElement) {
          message.textContent = "Waiting for SoundMask to restart and come back online. This page will refresh automatically once it responds again.";
        }
        if (summary instanceof HTMLElement) {
          summary.textContent = "Waiting for SoundMask to come back online.";
        }
        setBadge("pending", "Restarting");
        schedulePoll(2000);
      }
    };

    schedulePoll(1500);
  });
});
