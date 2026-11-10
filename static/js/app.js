/**
 * Habit Tracker - Minimal Vanilla JavaScript
 * Provides progressive enhancement for weekday selector and daily toggles.
 */

document.addEventListener("DOMContentLoaded", () => {
  // 1. Frequency (Weekdays & Weekly Target) Toggles in Habit Form
  const frequencySelect = document.getElementById("id_frequency");
  const weekdayContainer = document.getElementById("weekday-selector-container");
  const weeklyTargetContainer = document.getElementById("weekly-target-container");

  if (frequencySelect) {
    const updateFrequencyVisibility = () => {
      if (weekdayContainer) {
        weekdayContainer.style.display = (frequencySelect.value === "WEEKDAYS") ? "block" : "none";
      }
      if (weeklyTargetContainer) {
        weeklyTargetContainer.style.display = (frequencySelect.value === "WEEKLY_TARGET") ? "block" : "none";
      }
    };

    frequencySelect.addEventListener("change", updateFrequencyVisibility);
    updateFrequencyVisibility(); // Initial check on load
  }

  // 1b. Validation Rule / Rule Strategy Toggle in Habit Form
  const strategySelect = document.getElementById("id_rule_strategy_ref");
  const ruleSelect = document.getElementById("id_validation_rule");
  const timeContainer = document.getElementById("time-window-container");
  const numericContainer = document.getElementById("numeric-target-container");
  const evidenceContainer = document.getElementById("evidence-hint-container");
  const unitInput = document.getElementById("id_unit_label");

  let strategiesMeta = {};
  const metaElem = document.getElementById("rule-strategies-meta");
  if (metaElem) {
    try {
      strategiesMeta = JSON.parse(metaElem.textContent);
    } catch (e) {
      console.error("Failed to parse rule strategies meta", e);
    }
  }

  const updateStrategyVisibility = () => {
    let hasTime = false;
    let hasNumeric = false;
    let hasEvidence = false;

    if (strategySelect && strategySelect.value && strategiesMeta[strategySelect.value]) {
      const meta = strategiesMeta[strategySelect.value];
      const engine = meta.engine || "";
      hasTime = !!meta.has_time_window || engine === "TIME_WINDOW" || engine === "TIME_AND_EVIDENCE";
      hasNumeric = !!meta.requires_numeric || engine === "NUMERIC_TARGET";
      hasEvidence = !!meta.requires_evidence || engine === "EVIDENCE_FILE" || engine === "TIME_AND_EVIDENCE";
      if (meta.default_unit && unitInput && !unitInput.value.trim()) {
        unitInput.value = meta.default_unit;
      }
    } else if (ruleSelect) {
      const val = ruleSelect.value;
      hasTime = (val === "TIME_WINDOW" || val === "TIME_AND_EVIDENCE");
      hasNumeric = (val === "NUMERIC_TARGET");
      hasEvidence = (val === "EVIDENCE_FILE" || val === "TIME_AND_EVIDENCE");
    }

    if (timeContainer) {
      const hasTimeErrors = timeContainer.querySelector(".form-error");
      timeContainer.style.display = (hasTime || hasTimeErrors) ? "block" : "none";
    }
    if (numericContainer) {
      const hasNumericErrors = numericContainer.querySelector(".form-error");
      numericContainer.style.display = (hasNumeric || hasNumericErrors) ? "block" : "none";
    }
    if (evidenceContainer) evidenceContainer.style.display = hasEvidence ? "block" : "none";
  };

  if (strategySelect) {
    strategySelect.addEventListener("change", updateStrategyVisibility);
    updateStrategyVisibility();
  }
  if (ruleSelect) {
    ruleSelect.addEventListener("change", updateStrategyVisibility);
    if (!strategySelect) updateStrategyVisibility();
  }

  // 1c. Pixel Score Dynamic Allotment in Habit Form
  const habitTypeSelect = document.getElementById("id_habit_type");
  const pixelScoreInput = document.getElementById("id_pixel_score");
  const pixelScoreBadgeVal = document.getElementById("pixel-score-badge-val");

  if (pixelScoreInput && pixelScoreBadgeVal) {
    const updatePixelScoreBadge = () => {
      const val = parseInt(pixelScoreInput.value, 10);
      pixelScoreBadgeVal.textContent = isNaN(val) || val < 1 ? "2" : val;
    };

    pixelScoreInput.addEventListener("input", updatePixelScoreBadge);

    if (habitTypeSelect) {
      let previousType = habitTypeSelect.value;
      const onHabitTypeChange = () => {
        const currentType = habitTypeSelect.value;
        if (currentType === "GENERAL") {
          pixelScoreInput.value = "2";
          pixelScoreInput.readOnly = true;
          pixelScoreInput.style.backgroundColor = "var(--surface-raised)";
          pixelScoreInput.style.cursor = "not-allowed";
        } else if (currentType === "PREDEFINED_PURPOSE") {
          pixelScoreInput.readOnly = false;
          pixelScoreInput.style.backgroundColor = "";
          pixelScoreInput.style.cursor = "text";
          if (previousType === "GENERAL" || pixelScoreInput.value === "2" || pixelScoreInput.value === "10" || !pixelScoreInput.value) {
            pixelScoreInput.value = "5";
          }
        } else if (currentType === "EXPERT_PRESCRIBED") {
          pixelScoreInput.readOnly = false;
          pixelScoreInput.style.backgroundColor = "";
          pixelScoreInput.style.cursor = "text";
          if (previousType === "GENERAL" || pixelScoreInput.value === "2" || pixelScoreInput.value === "5" || !pixelScoreInput.value) {
            pixelScoreInput.value = "10";
          }
        }
        previousType = currentType;
        updatePixelScoreBadge();
      };

      habitTypeSelect.addEventListener("change", onHabitTypeChange);
      if (habitTypeSelect.value === "GENERAL") {
        pixelScoreInput.value = "2";
        pixelScoreInput.readOnly = true;
        pixelScoreInput.style.backgroundColor = "var(--surface-raised)";
        pixelScoreInput.style.cursor = "not-allowed";
      }
      updatePixelScoreBadge();
    }
  }

  // 2. Alert Dismissal
  const alerts = document.querySelectorAll(".alert");
  alerts.forEach((alert) => {
    const closeBtn = alert.querySelector(".alert-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        alert.style.opacity = "0";
        setTimeout(() => alert.remove(), 200);
      });
    }
  });

  // Helper: Acquire current GPS coordinates from browser Geolocation API
  function getCurrentCoordinates(timeoutMs = 10000) {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error("Geolocation is not supported by your browser or device."));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          resolve({
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
            accuracy: pos.coords.accuracy,
          });
        },
        (err) => {
          let msg = "Location access denied or unavailable.";
          if (err.code === 1) {
            msg = "Location permission denied. Please allow location access in your browser or phone to verify this habit.";
          } else if (err.code === 2) {
            msg = "Position unavailable. Please ensure your device GPS/location is turned on.";
          } else if (err.code === 3) {
            msg = "Location request timed out. Please try again.";
          }
          reject(new Error(msg));
        },
        {
          enableHighAccuracy: true,
          timeout: timeoutMs,
          maximumAge: 5000,
        }
      );
    });
  }

  // 3. Progressive Enhancement for Habit Completion Forms
  const completionForms = document.querySelectorAll(".ajax-completion-form");
  completionForms.forEach((form) => {
    form.addEventListener("submit", async (e) => {
      // If Javascript is supported, enhance completion toggle smoothly
      e.preventDefault();
      const submitBtn = form.querySelector("button[type='submit']");
      const origText = submitBtn ? submitBtn.innerHTML : "";
      if (submitBtn) submitBtn.disabled = true;

      // Handle Location Geofencing Check if required
      const isLocRestricted = form.getAttribute("data-is-location-restricted") === "true";
      if (isLocRestricted) {
        if (submitBtn) submitBtn.innerHTML = "<span>📍 Checking GPS...</span>";
        try {
          const coords = await getCurrentCoordinates();
          const latInput = form.querySelector(".input-latitude");
          const lngInput = form.querySelector(".input-longitude");
          if (latInput) latInput.value = coords.latitude;
          if (lngInput) lngInput.value = coords.longitude;
        } catch (geoErr) {
          alert("📍 Location check required: " + geoErr.message);
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = origText;
          }
          return;
        }
      }

      try {
        const formData = new FormData(form);
        let apiUrl = form.action;
        const completeMatch = form.action.match(/\/habits\/(\d+)\/complete\/?/);
        const undoMatch = form.action.match(/\/habits\/(\d+)\/undo\/?/);
        if (completeMatch) {
          apiUrl = `/api/v1/habits/${completeMatch[1]}/complete/`;
        } else if (undoMatch) {
          apiUrl = `/api/v1/habits/${undoMatch[1]}/undo/`;
        }

        const response = await fetch(apiUrl, {
          method: "POST",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": formData.get("csrfmiddlewaretoken"),
          },
          body: formData,
        });

        const result = await response.json().catch(() => null);
        if (response.ok && result && result.success) {
          console.info("[HabitPulse REST API] Success:", apiUrl, result);
          window.location.reload();
        } else {
          const errMsg = (result && result.error) ? result.error : "Failed to update habit.";
          alert(errMsg);
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = origText;
          }
        }
      } catch (err) {
        form.submit();
      }
    });
  });

  // 3b. Habit Completion Verification Modal
  const modal = document.getElementById("habit-verification-modal");
  if (modal) {
    const modalForm = document.getElementById("verification-form");
    const modalTitle = document.getElementById("modal-habit-title");
    const modalSubtitle = document.getElementById("modal-habit-subtitle");
    const modalDurationGroup = document.getElementById("modal-duration-group");
    const modalLoggedDuration = document.getElementById("modal-logged-duration");
    const modalDurationHelp = document.getElementById("modal-duration-help");
    const modalNumericGroup = document.getElementById("modal-numeric-group");
    const modalLoggedValue = document.getElementById("modal-logged-value");
    const modalUnitBadge = document.getElementById("modal-unit-badge");
    const modalNumericHelp = document.getElementById("modal-numeric-help");
    const modalEvidenceGroup = document.getElementById("modal-evidence-group");
    const modalEvidenceFile = document.getElementById("modal-evidence-file");
    const modalLocationGroup = document.getElementById("modal-location-group");
    const modalLocationBadge = document.getElementById("modal-location-badge");
    const modalLocationHelp = document.getElementById("modal-location-help");
    const modalLocationTargetName = document.getElementById("modal-location-target-name");
    const modalLatitude = document.getElementById("modal-latitude");
    const modalLongitude = document.getElementById("modal-longitude");
    const modalAlert = document.getElementById("modal-alert");
    const closeBtn = document.getElementById("close-verification-modal");
    const cancelBtn = document.getElementById("cancel-verification-modal");

    const closeModal = () => {
      modal.classList.remove("open");
      setTimeout(() => {
        modal.style.display = "none";
      }, 150);
      if (modalAlert) {
        modalAlert.style.display = "none";
        modalAlert.textContent = "";
      }
      if (modalLatitude) modalLatitude.value = "";
      if (modalLongitude) modalLongitude.value = "";
      if (modalLoggedDuration) modalLoggedDuration.value = "";
      if (modalForm) modalForm.reset();
    };

    const openModal = (btn) => {
      const habitName = btn.getAttribute("data-habit-name") || "Habit";
      const actionUrl = btn.getAttribute("data-action-url") || "";
      const requiresEvidence = btn.getAttribute("data-requires-evidence") === "true";
      const requiresNumeric = btn.getAttribute("data-requires-numeric") === "true";
      const requiresDuration = btn.getAttribute("data-requires-duration") === "true";
      const minDuration = btn.getAttribute("data-min-duration") || "";
      const isLocationRestricted = btn.getAttribute("data-is-location-restricted") === "true";
      const locationName = btn.getAttribute("data-location-name") || "the designated venue";
      const allowedRadius = btn.getAttribute("data-allowed-radius") || "150";
      const targetValue = btn.getAttribute("data-target-value") || "";
      const unitLabel = btn.getAttribute("data-unit-label") || "";
      const ruleDesc = btn.getAttribute("data-rule-desc") || "Verify completion";

      if (modalTitle) modalTitle.textContent = `Complete: ${habitName}`;
      if (modalSubtitle) modalSubtitle.textContent = ruleDesc;
      if (modalForm) modalForm.action = actionUrl;

      // Handle duration fields
      if (modalDurationGroup) {
        if (requiresDuration) {
          modalDurationGroup.style.display = "block";
          if (modalLoggedDuration) {
            modalLoggedDuration.required = true;
            modalLoggedDuration.placeholder = `Min: ${minDuration} minutes`;
          }
          if (modalDurationHelp) {
            modalDurationHelp.textContent = `Session requirement: at least ${minDuration} minutes logged.`;
          }
        } else {
          modalDurationGroup.style.display = "none";
          if (modalLoggedDuration) modalLoggedDuration.required = false;
        }
      }

      // Handle numeric fields
      if (modalNumericGroup) {
        if (requiresNumeric) {
          modalNumericGroup.style.display = "block";
          if (modalLoggedValue) {
            modalLoggedValue.required = true;
            modalLoggedValue.placeholder = `Target: ${targetValue} ${unitLabel}`;
          }
          if (modalUnitBadge) modalUnitBadge.textContent = unitLabel || "metric";
          if (modalNumericHelp) modalNumericHelp.textContent = `Goal threshold: at least ${targetValue} ${unitLabel}`;
        } else {
          modalNumericGroup.style.display = "none";
          if (modalLoggedValue) modalLoggedValue.required = false;
        }
      }

      // Handle evidence upload fields
      if (modalEvidenceGroup) {
        if (requiresEvidence) {
          modalEvidenceGroup.style.display = "block";
          if (modalEvidenceFile) modalEvidenceFile.required = true;
        } else {
          modalEvidenceGroup.style.display = "none";
          if (modalEvidenceFile) modalEvidenceFile.required = false;
        }
      }

      // Handle Location Geofencing
      if (modalLocationGroup) {
        if (isLocationRestricted) {
          modalLocationGroup.style.display = "block";
          if (modalLocationTargetName) modalLocationTargetName.textContent = locationName;
          if (modalLocationBadge) {
            modalLocationBadge.textContent = "Checking GPS...";
            modalLocationBadge.style.color = "#0284c7";
            modalLocationBadge.style.background = "rgba(56, 189, 248, 0.2)";
          }
          if (modalLocationHelp) {
            modalLocationHelp.textContent = `Acquiring your GPS coordinates to verify you are within ${allowedRadius}m of ${locationName}...`;
          }

          getCurrentCoordinates()
            .then((coords) => {
              if (modalLatitude) modalLatitude.value = coords.latitude;
              if (modalLongitude) modalLongitude.value = coords.longitude;
              if (modalLocationBadge) {
                modalLocationBadge.textContent = "✓ GPS Acquired";
                modalLocationBadge.style.color = "#10b981";
                modalLocationBadge.style.background = "rgba(16, 185, 129, 0.2)";
              }
              if (modalLocationHelp) {
                modalLocationHelp.textContent = `Location verified: ${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}. Ready to submit!`;
              }
            })
            .catch((geoErr) => {
              if (modalLocationBadge) {
                modalLocationBadge.textContent = "⚠️ GPS Needed";
                modalLocationBadge.style.color = "#ef4444";
                modalLocationBadge.style.background = "rgba(239, 68, 68, 0.2)";
              }
              if (modalLocationHelp) {
                modalLocationHelp.textContent = geoErr.message;
              }
            });
        } else {
          modalLocationGroup.style.display = "none";
        }
      }

      if (modalAlert) {
        modalAlert.style.display = "none";
        modalAlert.textContent = "";
      }

      modal.style.display = "flex";
      requestAnimationFrame(() => {
        modal.classList.add("open");
      });
    };

    document.querySelectorAll(".open-completion-modal").forEach((btn) => {
      btn.addEventListener("click", () => openModal(btn));
    });

    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (cancelBtn) cancelBtn.addEventListener("click", closeModal);

    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeModal();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modal.classList.contains("open")) {
        closeModal();
      }
    });

    // AJAX form submission for verification modal
    if (modalForm) {
      modalForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const submitBtn = document.getElementById("submit-verification-btn");
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.textContent = "Verifying...";
        }

        // Check if location is required and not yet acquired
        if (modalLocationGroup && modalLocationGroup.style.display !== "none") {
          if (!modalLatitude || !modalLatitude.value || !modalLongitude || !modalLongitude.value) {
            try {
              const coords = await getCurrentCoordinates();
              if (modalLatitude) modalLatitude.value = coords.latitude;
              if (modalLongitude) modalLongitude.value = coords.longitude;
            } catch (geoErr) {
              if (modalAlert) {
                modalAlert.textContent = "📍 " + geoErr.message;
                modalAlert.style.display = "block";
              } else {
                alert("📍 " + geoErr.message);
              }
              if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = "✓ Submit & Complete";
              }
              return;
            }
          }
        }

        try {
          const formData = new FormData(modalForm);
          let apiUrl = modalForm.action;
          const completeMatch = modalForm.action.match(/\/habits\/(\d+)\/complete\/?/);
          if (completeMatch) {
            apiUrl = `/api/v1/habits/${completeMatch[1]}/complete/`;
          }
          const response = await fetch(apiUrl, {
            method: "POST",
            headers: {
              "X-Requested-With": "XMLHttpRequest",
              "X-CSRFToken": formData.get("csrfmiddlewaretoken"),
            },
            body: formData,
          });

          if (response.ok) {
            window.location.reload();
          } else {
            const data = await response.json().catch(() => null);
            const errText = (data && data.error) ? data.error : "Failed to verify completion. Please check requirements.";
            if (modalAlert) {
              modalAlert.textContent = errText;
              modalAlert.style.display = "block";
            } else {
              alert(errText);
            }
            if (submitBtn) {
              submitBtn.disabled = false;
              submitBtn.textContent = "✓ Submit & Complete";
            }
          }
        } catch (err) {
          modalForm.submit();
        }
      });
    }
  }

  // 3c. Geofencing Coordinates Detection in Habit Creation and Adoption Forms
  const setupLocationDetection = (btnId, statusId, latInputId, lngInputId, toggleCheckboxId, containerId) => {
    const btn = document.getElementById(btnId);
    const statusEl = document.getElementById(statusId);
    const latInput = document.getElementById(latInputId);
    const lngInput = document.getElementById(lngInputId);
    const checkbox = document.getElementById(toggleCheckboxId);
    const container = document.getElementById(containerId);

    if (checkbox && container) {
      const toggleContainer = () => {
        container.style.display = checkbox.checked ? "block" : "none";
      };
      checkbox.addEventListener("change", toggleContainer);
    }

    if (btn && latInput && lngInput) {
      btn.addEventListener("click", async () => {
        const origText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = "<span>📍 Acquiring GPS...</span>";
        if (statusEl) {
          statusEl.style.display = "block";
          statusEl.style.background = "rgba(56, 189, 248, 0.12)";
          statusEl.style.color = "#0284c7";
          statusEl.textContent = "Requesting device GPS coordinates...";
        }

        try {
          const coords = await getCurrentCoordinates();
          latInput.value = coords.latitude.toFixed(6);
          lngInput.value = coords.longitude.toFixed(6);
          if (statusEl) {
            statusEl.style.background = "rgba(16, 185, 129, 0.12)";
            statusEl.style.color = "#10b981";
            statusEl.innerHTML = `✓ Coordinates detected: <strong>${coords.latitude.toFixed(6)}, ${coords.longitude.toFixed(6)}</strong> (Accuracy: ±${Math.round(coords.accuracy || 10)}m)`;
          }
        } catch (err) {
          if (statusEl) {
            statusEl.style.background = "rgba(239, 68, 68, 0.12)";
            statusEl.style.color = "#ef4444";
            statusEl.textContent = "⚠️ " + err.message;
          } else {
            alert(err.message);
          }
        } finally {
          btn.disabled = false;
          btn.innerHTML = origText;
        }
      });
    }
  };

  setupLocationDetection(
    "btn-detect-location",
    "location-detection-status",
    "id_target_latitude",
    "id_target_longitude",
    "id_is_location_restricted",
    "location-geofence-container"
  );

  setupLocationDetection(
    "btn-adopt-detect-location",
    "adopt-location-detection-status",
    "id_adopt_target_latitude",
    "id_adopt_target_longitude",
    "id_adopt_is_location_restricted",
    "adopt-location-fields"
  );

  // 3d. Google Maps URL or Coordinates Parser & Auto-Filler
  function parseGoogleMapsUrlOrCoordsClient(text) {
    if (!text) return null;
    text = text.trim();

    // 1. Check direct raw coordinates: "12.978369, 77.640835" or "12.978369,77.640835"
    const mRaw = text.match(/(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)/);
    // 2. Check @lat,lng format
    const mAt = text.match(/@(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)/);
    // 3. Check !3dlat!4dlng protobuf format
    const m3d = text.match(/!3d(-?\d{1,2}\.\d+)!4d(-?\d{1,3}\.\d+)/);
    // 4. Check query params: q=lat,lng or query=lat,lng or ll=lat,lng
    const mQ = text.match(/[?&](?:q|query|ll|center)=(-?\d{1,2}\.\d+)[,+](-?\d{1,3}\.\d+)/);
    // 5. Check place name
    const mPlace = text.match(/\/maps\/place\/([^/@?]+)/);
    let placeName = null;
    if (mPlace) {
      try {
        placeName = decodeURIComponent(mPlace[1].replace(/\+/g, " "));
      } catch (e) {
        placeName = mPlace[1].replace(/\+/g, " ");
      }
    }

    let lat = null;
    let lng = null;
    if (m3d) {
      lat = parseFloat(m3d[1]);
      lng = parseFloat(m3d[2]);
    } else if (mAt) {
      lat = parseFloat(mAt[1]);
      lng = parseFloat(mAt[2]);
    } else if (mQ) {
      lat = parseFloat(mQ[1]);
      lng = parseFloat(mQ[2]);
    } else if (mRaw) {
      lat = parseFloat(mRaw[1]);
      lng = parseFloat(mRaw[2]);
    }

    if (lat !== null && lng !== null) {
      return {
        latitude: lat,
        longitude: lng,
        locationName: placeName,
      };
    }
    return null;
  }

  const setupGoogleMapsExtractor = (inputId, btnId, statusId, latInputId, lngInputId, nameInputId) => {
    const inputEl = document.getElementById(inputId);
    const btnEl = document.getElementById(btnId);
    const statusEl = document.getElementById(statusId);
    const latInput = document.getElementById(latInputId);
    const lngInput = document.getElementById(lngInputId);
    const nameInput = document.getElementById(nameInputId);

    if (!inputEl || !latInput || !lngInput) return;

    const clearLocationErrors = () => {
      const container = inputEl.closest(".m2m-plotted-card") || inputEl.closest("#location-geofence-container") || inputEl.closest("#adopt-location-fields");
      if (container) {
        container.querySelectorAll(".form-error").forEach((el) => el.remove());
      }
    };

    const highlightSuccess = () => {
      [latInput, lngInput, nameInput].forEach((inp) => {
        if (inp) {
          inp.style.transition = "box-shadow 0.3s, border-color 0.3s";
          inp.style.borderColor = "#10b981";
          inp.style.boxShadow = "0 0 0 3px rgba(16, 185, 129, 0.25)";
          setTimeout(() => {
            inp.style.boxShadow = "";
          }, 2500);
        }
      });
    };

    const performExtraction = async () => {
      const val = (inputEl.value || "").trim();
      if (!val) {
        if (statusEl) {
          statusEl.style.display = "block";
          statusEl.style.background = "rgba(239, 68, 68, 0.12)";
          statusEl.style.color = "#ef4444";
          statusEl.textContent = "Please paste a Google Maps link or coordinates first.";
        }
        return false;
      }

      // Fast Client-side regex parsing
      const clientResult = parseGoogleMapsUrlOrCoordsClient(val);
      if (clientResult) {
        latInput.value = clientResult.latitude.toFixed(6);
        lngInput.value = clientResult.longitude.toFixed(6);
        if (nameInput && clientResult.locationName && (!nameInput.value.trim() || nameInput.value.trim().length <= 3)) {
          nameInput.value = clientResult.locationName;
        }
        clearLocationErrors();
        highlightSuccess();
        if (statusEl) {
          statusEl.style.display = "block";
          statusEl.style.background = "rgba(16, 185, 129, 0.15)";
          statusEl.style.color = "#10b981";
          statusEl.style.border = "1px solid rgba(16, 185, 129, 0.4)";
          const namePart = clientResult.locationName ? ` (${clientResult.locationName})` : "";
          statusEl.innerHTML = `✅ <strong>Coordinates Auto-Filled:</strong> ${clientResult.latitude.toFixed(6)}, ${clientResult.longitude.toFixed(6)}${namePart}`;
        }
        return true;
      }

      // If shortened URL e.g. maps.app.goo.gl, resolve via backend endpoint
      if (val.startsWith("http://") || val.startsWith("https://")) {
        const origBtnText = btnEl ? btnEl.innerHTML : "";
        if (btnEl) {
          btnEl.disabled = true;
          btnEl.textContent = "⏳ Extracting...";
        }
        if (statusEl) {
          statusEl.style.display = "block";
          statusEl.style.background = "rgba(56, 189, 248, 0.12)";
          statusEl.style.color = "#0284c7";
          statusEl.textContent = "Resolving Google Maps location and extracting coordinates...";
        }

        try {
          const resp = await fetch(`/api/v1/resolve-map-url/?url=${encodeURIComponent(val)}`);
          const data = await resp.json();
          if (resp.ok && data.success) {
            latInput.value = Number(data.latitude).toFixed(6);
            lngInput.value = Number(data.longitude).toFixed(6);
            if (nameInput && data.location_name && (!nameInput.value.trim() || nameInput.value.trim().length <= 3)) {
              nameInput.value = data.location_name;
            }
            clearLocationErrors();
            highlightSuccess();
            if (statusEl) {
              statusEl.style.background = "rgba(16, 185, 129, 0.15)";
              statusEl.style.color = "#10b981";
              statusEl.style.border = "1px solid rgba(16, 185, 129, 0.4)";
              const namePart = data.location_name ? ` (${data.location_name})` : "";
              statusEl.innerHTML = `✅ <strong>Coordinates Auto-Filled:</strong> ${data.latitude}, ${data.longitude}${namePart}`;
            }
            return true;
          } else {
            if (statusEl) {
              statusEl.style.background = "rgba(239, 68, 68, 0.12)";
              statusEl.style.color = "#ef4444";
              statusEl.style.border = "1px solid rgba(239, 68, 68, 0.3)";
              statusEl.textContent = "⚠️ " + (data.error || "Could not detect GPS coordinates from this link.");
            }
            return false;
          }
        } catch (err) {
          if (statusEl) {
            statusEl.style.background = "rgba(239, 68, 68, 0.12)";
            statusEl.style.color = "#ef4444";
            statusEl.textContent = "⚠️ Failed to resolve link. Please enter coordinates directly.";
          }
          return false;
        } finally {
          if (btnEl) {
            btnEl.disabled = false;
            btnEl.innerHTML = origBtnText;
          }
        }
      } else {
        if (statusEl) {
          statusEl.style.display = "block";
          statusEl.style.background = "rgba(239, 68, 68, 0.12)";
          statusEl.style.color = "#ef4444";
          statusEl.textContent = "⚠️ Unrecognized format. Please paste a Google Maps link or coordinates (e.g. 12.9783, 77.6408).";
        }
        return false;
      }
    };

    if (btnEl) btnEl.addEventListener("click", performExtraction);

    inputEl.addEventListener("paste", (e) => {
      const pasted = (e.clipboardData || window.clipboardData)?.getData("text");
      if (pasted && pasted.trim()) {
        inputEl.value = pasted.trim();
        performExtraction();
      } else {
        setTimeout(performExtraction, 40);
      }
    });

    let debounceTimer = null;
    inputEl.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      if (inputEl.value.trim().length > 6) {
        debounceTimer = setTimeout(performExtraction, 350);
      }
    });

    inputEl.addEventListener("change", performExtraction);

    // Form submit guard: if coords missing but URL present, extract before submitting
    const parentForm = inputEl.closest("form");
    if (parentForm) {
      parentForm.addEventListener("submit", async function(e) {
        const isLocCb = parentForm.querySelector("#id_is_location_restricted, #id_adopt_is_location_restricted");
        if (isLocCb && isLocCb.checked) {
          if ((!latInput.value.trim() || !lngInput.value.trim()) && inputEl.value.trim().length > 5) {
            e.preventDefault();
            const success = await performExtraction();
            if (success) {
              parentForm.submit();
            }
          }
        }
      });
    }
  };

  setupGoogleMapsExtractor(
    "id_map_url_input",
    "btn-parse-map-url",
    "map-url-status",
    "id_target_latitude",
    "id_target_longitude",
    "id_location_name"
  );

  setupGoogleMapsExtractor(
    "id_adopt_map_url_input",
    "btn-adopt-parse-map-url",
    "adopt-map-url-status",
    "id_adopt_target_latitude",
    "id_adopt_target_longitude",
    "id_adopt_location_name"
  );

  // 4. Navigation & Dropdown Toggle
  const closeAllDropdowns = () => {
    document.querySelectorAll(".dropdown-menu.show").forEach((m) => m.classList.remove("show"));
  };

  const dropdownToggles = document.querySelectorAll(".dropdown-toggle");
  dropdownToggles.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const parentDropdown = btn.closest(".dropdown");
      const menu = parentDropdown ? parentDropdown.querySelector(".dropdown-menu") : null;
      if (menu) {
        const isOpen = menu.classList.contains("show");
        // Close all open dropdowns first
        closeAllDropdowns();
        if (!isOpen) {
          menu.classList.add("show");
        }
      }
    });
  });

  // Close dropdowns on outside click or Escape key
  document.addEventListener("click", () => {
    closeAllDropdowns();
  });

  // 4b. Mobile Sidebar Drawer Toggle
  const sidebarToggleBtn = document.getElementById("sidebarToggleBtn");
  const sidebarCloseBtn = document.getElementById("sidebarCloseBtn");
  const sidebarBackdrop = document.getElementById("sidebarBackdrop");
  const appSidebar = document.getElementById("appSidebar");

  const toggleSidebar = (shouldOpen) => {
    if (!appSidebar) return;
    const isCurrentlyOpen = appSidebar.classList.contains("sidebar-open");
    const open = shouldOpen !== undefined ? shouldOpen : !isCurrentlyOpen;
    if (open) {
      appSidebar.classList.add("sidebar-open");
      if (sidebarBackdrop) sidebarBackdrop.classList.add("active");
      document.body.classList.add("sidebar-locked");
    } else {
      appSidebar.classList.remove("sidebar-open");
      if (sidebarBackdrop) sidebarBackdrop.classList.remove("active");
      document.body.classList.remove("sidebar-locked");
    }
  };

  if (sidebarToggleBtn) {
    sidebarToggleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleSidebar();
    });
  }
  if (sidebarCloseBtn) {
    sidebarCloseBtn.addEventListener("click", () => toggleSidebar(false));
  }
  if (sidebarBackdrop) {
    sidebarBackdrop.addEventListener("click", () => toggleSidebar(false));
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeAllDropdowns();
      toggleSidebar(false);
    }
  });

  // 4c. Sidebar Dropdown Accordion Toggle
  document.querySelectorAll(".sidebar-dropdown-toggle").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const parentItem = btn.closest(".sidebar-dropdown-item");
      if (parentItem) {
        const isOpen = parentItem.classList.contains("open");
        parentItem.classList.toggle("open");
        btn.setAttribute("aria-expanded", !isOpen);
      }
    });
  });

  // 5. Theme Switcher System
  const themeIcons = {
    ice: "❄️",
    light: "☀️",
    rose: "🌸",
    dark: "🌙"
  };

  const applyTheme = (themeName) => {
    document.documentElement.setAttribute("data-theme", themeName);
    localStorage.setItem("habitpulse_theme", themeName);

    // Update active checkmarks for button options
    document.querySelectorAll(".theme-option").forEach((opt) => {
      if (opt.getAttribute("data-theme-value") === themeName) {
        opt.classList.add("active");
      } else {
        opt.classList.remove("active");
      }
    });

    // Update theme select inputs if present
    document.querySelectorAll(".theme-select-control").forEach((sel) => {
      sel.value = themeName;
    });

    // Update icons on toggle buttons and labels
    document.querySelectorAll(".theme-icon").forEach((el) => {
      if (themeIcons[themeName]) {
        el.textContent = themeIcons[themeName];
      }
    });
  };

  // Initialize theme state
  const activeSavedTheme = localStorage.getItem("habitpulse_theme") || "ice";
  applyTheme(activeSavedTheme);

  // Bind click handlers for button-based theme options
  document.querySelectorAll(".theme-option").forEach((opt) => {
    opt.addEventListener("click", (e) => {
      e.preventDefault();
      const selectedTheme = opt.getAttribute("data-theme-value");
      if (selectedTheme) {
        applyTheme(selectedTheme);
      }
      closeAllDropdowns();
    });
  });

  // Bind change handlers for select-based theme dropdown
  document.querySelectorAll(".theme-select-control").forEach((sel) => {
    sel.addEventListener("click", (e) => {
      e.stopPropagation();
    });
    sel.addEventListener("change", (e) => {
      const selectedTheme = e.target.value;
      if (selectedTheme) {
        applyTheme(selectedTheme);
      }
      closeAllDropdowns();
    });
  });

  // 6. Global Password Visibility Toggle
  const EYE_ICON_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;
  const EYE_OFF_ICON_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>`;

  document.querySelectorAll(".password-toggle-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const targetId = btn.getAttribute("data-target");
      const wrapper = btn.closest(".password-input-wrapper");
      const input = targetId ? document.getElementById(targetId) : (wrapper ? wrapper.querySelector("input") : null);
      if (input) {
        const isPassword = input.getAttribute("type") === "password";
        input.setAttribute("type", isPassword ? "text" : "password");
        btn.innerHTML = isPassword ? EYE_OFF_ICON_SVG : EYE_ICON_SVG;
        btn.setAttribute("title", isPassword ? "Hide password" : "Show password");
        btn.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
      }
    });
  });

  // 7. Habits Hub 3-Section Sub Header Tabs
  const habitTabButtons = document.querySelectorAll(".habit-sub-header-btn");
  const habitSections = document.querySelectorAll(".habit-section");

  if (habitTabButtons.length > 0 && habitSections.length > 0) {
    const activateTab = (targetId) => {
      // Normalize targetId
      let normalizedId = targetId;
      if (targetId === "user_created" || targetId === "user-created") normalizedId = "my-habits";
      if (targetId === "predefined") normalizedId = "predefined-habits";
      if (targetId === "expert") normalizedId = "expert-habits";

      habitTabButtons.forEach((btn) => {
        const isMatch = btn.getAttribute("data-target") === normalizedId;
        btn.classList.toggle("active", isMatch);
        btn.setAttribute("aria-selected", isMatch ? "true" : "false");
      });

      habitSections.forEach((sec) => {
        const isMatch = sec.id === normalizedId;
        sec.classList.toggle("active", isMatch);
      });
    };

    habitTabButtons.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const targetId = btn.getAttribute("data-target");
        if (targetId) {
          activateTab(targetId);
          if (window.history && window.history.replaceState) {
            window.history.replaceState(null, "", `#${targetId}`);
          } else {
            window.location.hash = `#${targetId}`;
          }
        }
      });
    });

    // Handle hash on load or popstate
    const handleUrlHash = () => {
      const hash = window.location.hash.replace("#", "");
      if (hash && (hash === "my-habits" || hash === "predefined-habits" || hash === "expert-habits" || hash === "user-created" || hash === "predefined" || hash === "expert")) {
        activateTab(hash);
      } else {
        const urlParams = new URLSearchParams(window.location.search);
        const tabParam = urlParams.get("tab");
        if (tabParam) {
          activateTab(tabParam);
        }
      }
    };

    handleUrlHash();
    window.addEventListener("hashchange", handleUrlHash);
  }

  // 8. Idempotent Form Submission & Multi-Click Debouncing
  document.querySelectorAll(".js-idempotent-form, #habit-form").forEach((form) => {
    form.addEventListener("submit", function (e) {
      if (form.dataset.submitting === "true") {
        e.preventDefault();
        return false;
      }

      const submitBtn = form.querySelector("button[type='submit']");
      if (submitBtn) {
        form.dataset.submitting = "true";
        const originalText = submitBtn.innerHTML;
        submitBtn.dataset.originalText = originalText;

        let loadingText = "Saving...";
        const lower = originalText.toLowerCase();
        if (lower.includes("create")) {
          loadingText = "Creating Habit...";
        } else if (lower.includes("publish")) {
          loadingText = "Publishing...";
        } else if (lower.includes("add")) {
          loadingText = "Adding...";
        }

        submitBtn.disabled = true;
        submitBtn.style.opacity = "0.75";
        submitBtn.style.cursor = "not-allowed";
        submitBtn.innerHTML = `<span style="display: inline-block; width: 13px; height: 13px; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; vertical-align: middle; margin-right: 6px; animation: spin 0.75s linear infinite;"></span>${loadingText}`;
      }
    });
  });

  // 9. Client Timezone Synchronization for Accurate Time Window Validation
  try {
    const clientTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (clientTz) {
      const match = document.cookie.match(/(?:^|; )django_timezone=([^;]*)/);
      const currentTzCookie = match ? decodeURIComponent(match[1]) : null;
      if (currentTzCookie !== clientTz) {
        document.cookie = `django_timezone=${encodeURIComponent(clientTz)}; path=/; max-age=31536000; SameSite=Lax`;
      }
    }
  } catch (e) {
    // Graceful fallback if Intl API is unavailable
  }

  // 10. Live Dynamic Time Window Status & Real-Time Activation
  const updateTimeWindowHabits = () => {
    const containers = document.querySelectorAll('.habit-action-container[data-has-time-window="true"]');
    if (!containers.length) return;

    const now = new Date();
    const currentSeconds = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();

    containers.forEach((container) => {
      const startStr = container.getAttribute("data-window-start");
      const endStr = container.getAttribute("data-window-end");
      const startDisplay = container.getAttribute("data-window-start-display") || startStr;
      const endDisplay = container.getAttribute("data-window-end-display") || endStr;

      if (!startStr || !endStr) return;

      const [sh, sm, ss = 0] = startStr.split(":").map(Number);
      const [eh, em, es = 0] = endStr.split(":").map(Number);

      const startSeconds = sh * 3600 + sm * 60 + ss;
      // Minute inclusive: if end time seconds is 0, include up to 59 seconds of that minute
      const endSeconds = eh * 3600 + em * 60 + (es === 0 ? 59 : es);

      const lockedBtn = container.querySelector(".time-window-locked-btn");
      const statusText = container.querySelector(".time-window-status-text");
      const activeAction = container.querySelector(".time-window-active-action");

      if (currentSeconds < startSeconds) {
        // Locked: too early
        if (lockedBtn) {
          lockedBtn.style.display = "inline-block";
          if (statusText) statusText.textContent = `Locked until ${startDisplay}`;
          lockedBtn.title = `Locked until ${startDisplay}`;
        }
        if (activeAction) activeAction.style.display = "none";
      } else if (currentSeconds <= endSeconds) {
        // Active: inside allowed window! Real-time activation without page reload
        if (lockedBtn) lockedBtn.style.display = "none";
        if (activeAction) activeAction.style.display = "inline-block";
      } else {
        // Expired: window closed
        if (lockedBtn) {
          lockedBtn.style.display = "inline-block";
          if (statusText) statusText.textContent = `Window closed at ${endDisplay}`;
          lockedBtn.title = `Window closed at ${endDisplay}`;
        }
        if (activeAction) activeAction.style.display = "none";
      }
    });
  };

  // Run on load and every second for instantaneous real-time UI transitions
  updateTimeWindowHabits();
  setInterval(updateTimeWindowHabits, 15000);
// Redundant background telemetry fetch calls removed (PERF-07)

  // 13. Foldable & Expandable Pixel Score Allocation Section
  const pixelSection = document.getElementById("pixel-score-section");
  const pixelToggleHeader = document.getElementById("pixel-score-header-toggle");
  const pixelToggleBtn = document.getElementById("pixel-score-toggle-btn");
  const pixelContent = document.getElementById("pixel-score-content");

  if (pixelSection && pixelContent) {
    const btnText = pixelSection.querySelector(".pixel-score-btn-text");
    const btnChevron = pixelSection.querySelector(".pixel-score-btn-chevron");
    const statusBadge = pixelSection.querySelector(".pixel-score-status-badge");

    const setExpanded = (isExpanded, savePreference = true) => {
      if (isExpanded) {
        pixelContent.style.display = "block";
        if (pixelToggleHeader) pixelToggleHeader.setAttribute("aria-expanded", "true");
        if (btnText) btnText.textContent = "Fold";
        if (btnChevron) btnChevron.style.transform = "rotate(180deg)";
        if (statusBadge) {
          statusBadge.textContent = "Expanded";
          statusBadge.style.color = "var(--success, #10b981)";
        }
      } else {
        pixelContent.style.display = "none";
        if (pixelToggleHeader) pixelToggleHeader.setAttribute("aria-expanded", "false");
        if (btnText) btnText.textContent = "Expand";
        if (btnChevron) btnChevron.style.transform = "rotate(0deg)";
        if (statusBadge) {
          statusBadge.textContent = "Foldable";
          statusBadge.style.color = "var(--primary)";
        }
      }
      if (savePreference) {
        localStorage.setItem("habitpulse_pixel_alloc_expanded", isExpanded ? "true" : "false");
      }
    };

    // By default keep folded (collapsed) unless the user previously explicitly expanded it
    const savedState = localStorage.getItem("habitpulse_pixel_alloc_expanded");
    setExpanded(savedState === "true", false);

    const toggle = (e) => {
      e.stopPropagation();
      const isCurrentlyExpanded = pixelContent.style.display === "block";
      setExpanded(!isCurrentlyExpanded, true);
    };

    if (pixelToggleHeader) {
      pixelToggleHeader.addEventListener("click", toggle);
      pixelToggleHeader.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          toggle(e);
        }
      });
    }
    if (pixelToggleBtn) {
      pixelToggleBtn.addEventListener("click", toggle);
    }
  }

  // 4d. Habit Notifications Bell Dropdown & Filtering
  const habitNotifTabs = document.querySelectorAll(".habit-notif-tab");
  if (habitNotifTabs.length > 0) {
    habitNotifTabs.forEach((tab) => {
      tab.addEventListener("click", (e) => {
        e.stopPropagation();
        habitNotifTabs.forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        const filter = tab.dataset.filter;
        const items = document.querySelectorAll(".habit-notif-item");
        items.forEach((item) => {
          if (filter === "all") {
            item.style.display = "";
          } else if (filter === "pending") {
            item.style.display = item.dataset.status === "pending" ? "" : "none";
          } else if (filter === "completed") {
            item.style.display = item.dataset.status === "completed" ? "" : "none";
          }
        });
      });
    });
  }

  // Prevent dropdown closing when clicking inside the notification menu (tabs, scrollbar, content)
  const habitNotifMenu = document.getElementById("habitNotificationMenu");
  if (habitNotifMenu) {
    habitNotifMenu.addEventListener("click", (e) => {
      // Allow link navigation to proceed normally without stopping
      if (!e.target.closest("a")) {
        e.stopPropagation();
      }
    });
  }


  // 7. Progressive Web App (PWA) Install Prompt Handler
  let deferredInstallPrompt = null;
  const pwaInstallBtn = document.getElementById("pwaInstallBtn");

  const isAppInstalledOnDevice = () => {
    // 1. Running in standalone display mode (installed app window)
    if (window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true) {
      return true;
    }
    // 2. Previously marked as installed in localStorage for this device
    if (localStorage.getItem("habitpulse_installed") === "true") {
      return true;
    }
    return false;
  };

  // If already installed on this device, hide the button immediately
  if (isAppInstalledOnDevice() && pwaInstallBtn) {
    pwaInstallBtn.style.display = "none";
  }

  // Check getInstalledRelatedApps API if supported by browser
  if ("getInstalledRelatedApps" in navigator) {
    navigator.getInstalledRelatedApps().then((relatedApps) => {
      if (relatedApps && relatedApps.length > 0) {
        localStorage.setItem("habitpulse_installed", "true");
        if (pwaInstallBtn) pwaInstallBtn.style.display = "none";
      }
    }).catch(() => {});
  }

  // Listen for beforeinstallprompt event (fired by browser only when app is not installed)
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;

    // Reveal the single stylish install button if not installed
    if (!isAppInstalledOnDevice() && pwaInstallBtn) {
      pwaInstallBtn.style.display = "inline-flex";
    }
  });

  const triggerPwaInstall = async (e) => {
    if (e) e.preventDefault();
    if (!deferredInstallPrompt) return;
    deferredInstallPrompt.prompt();
    const { outcome } = await deferredInstallPrompt.userChoice;
    if (outcome === "accepted") {
      localStorage.setItem("habitpulse_installed", "true");
      if (pwaInstallBtn) pwaInstallBtn.style.display = "none";
    }
    deferredInstallPrompt = null;
  };

  if (pwaInstallBtn) {
    pwaInstallBtn.addEventListener("click", triggerPwaInstall);
  }

  // When app finishes installation on this device, remember and hide permanently
  window.addEventListener("appinstalled", () => {
    localStorage.setItem("habitpulse_installed", "true");
    if (pwaInstallBtn) pwaInstallBtn.style.display = "none";
    deferredInstallPrompt = null;
    console.log("[PWA] HabitPulse installed on this device; install button permanently hidden.");
  });

  // Also listen for display-mode changes
  window.matchMedia("(display-mode: standalone)").addEventListener("change", (e) => {
    if (e.matches) {
      localStorage.setItem("habitpulse_installed", "true");
      if (pwaInstallBtn) pwaInstallBtn.style.display = "none";
    }
  });

});
