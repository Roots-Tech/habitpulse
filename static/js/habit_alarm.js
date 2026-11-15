/**
 * HabitPulse Habit Alarm & Free Intimation System
 * Supports:
 * 1. Native Web Push Notifications (via Service Worker) to Mobile Phones & Desktops
 * 2. Windows Notification Center / Action Center Desktop Notifications
 * 3. In-App Web Audio Alarm Chimes (Zero-asset oscillator)
 * 4. Client-side Real-time Alarm Scheduler & Snooze System
 * 5. 1-Click Phone Calendar (.ics) Native Alarm Sync
 */

(function () {
  'use strict';

  // -------------------------------------------------------------------------
  // 1. Web Audio Alarm Chime Generator (Pure Web Audio API - Zero External MP3)
  // -------------------------------------------------------------------------
  var audioCtx = null;

  function getAudioContext() {
    if (!audioCtx) {
      var AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        audioCtx = new AudioContextClass();
      }
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    return audioCtx;
  }

  function playAlarmChime() {
    try {
      var ctx = getAudioContext();
      if (!ctx) return;

      var now = ctx.currentTime;
      var notes = [
        { freq: 523.25, start: 0.0, dur: 0.18 }, // C5
        { freq: 659.25, start: 0.18, dur: 0.18 }, // E5
        { freq: 783.99, start: 0.36, dur: 0.35 }  // G5
      ];

      notes.forEach(function (n) {
        var osc = ctx.createOscillator();
        var gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(n.freq, now + n.start);

        gain.gain.setValueAtTime(0, now + n.start);
        gain.gain.linearRampToValueAtTime(0.25, now + n.start + 0.04);
        gain.gain.exponentialRampToValueAtTime(0.001, now + n.start + n.dur);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(now + n.start);
        osc.stop(now + n.start + n.dur);
      });
    } catch (e) {
      console.warn('[HabitAlarm] Audio playback unavailable:', e);
    }
  }

  // Helper: Convert VAPID base64 string to Uint8Array for PushManager
  function urlB64ToUint8Array(base64String) {
    var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    var rawData = window.atob(base64);
    var outputArray = new Uint8Array(rawData.length);
    for (var i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  // -------------------------------------------------------------------------
  // 2. Web Push Registration (Free Native Push)
  // -------------------------------------------------------------------------
  function setupWebPushSubscription() {
    var vapidMeta = document.querySelector('meta[name="vapid-public-key"]');
    var vapidKey = vapidMeta ? vapidMeta.getAttribute('content') : '';

    if (!vapidKey || !('serviceWorker' in navigator) || !('PushManager' in window)) {
      return Promise.resolve(null);
    }

    if (Notification.permission !== 'granted') {
      return Promise.resolve(null);
    }

    return navigator.serviceWorker.ready.then(function (reg) {
      return reg.pushManager.getSubscription().then(function (sub) {
        if (sub) {
          return sendSubscriptionToServer(sub);
        }
        return reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlB64ToUint8Array(vapidKey)
        }).then(function (newSub) {
          return sendSubscriptionToServer(newSub);
        });
      });
    }).catch(function (err) {
      console.log('[HabitAlarm] Push registration notice:', err);
    });
  }

  function sendSubscriptionToServer(subscription) {
    var key = subscription.getKey ? subscription.getKey('p256dh') : null;
    var auth = subscription.getKey ? subscription.getKey('auth') : null;

    var p256dh = key ? btoa(String.fromCharCode.apply(null, new Uint8Array(key))) : '';
    var authKey = auth ? btoa(String.fromCharCode.apply(null, new Uint8Array(auth))) : '';

    var csrfToken = getCsrfToken();

    return fetch('/api/v1/push/subscribe/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({
        endpoint: subscription.endpoint,
        keys: {
          p256dh: p256dh,
          auth: authKey
        }
      })
    }).catch(function (e) {
      console.warn('[HabitAlarm] Failed to save push subscription:', e);
    });
  }

  function getCsrfToken() {
    var cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
    if (cookieMatch) return cookieMatch[1];
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : '';
  }

  // -------------------------------------------------------------------------
  // 3. System / Windows Desktop Notification Center Integration
  // -------------------------------------------------------------------------
  function showSystemNotification(title, body, habitId, url) {
    if (!('Notification' in window) || Notification.permission !== 'granted') {
      return;
    }

    var options = {
      body: body,
      icon: '/static/images/pwa_icon_192.png',
      badge: '/static/images/habit_icon.png',
      tag: 'habit-alarm-' + (habitId || 'general'),
      renotify: true,
      requireInteraction: true,
      vibrate: [250, 100, 250, 100, 250],
      data: {
        url: url || '/habits/',
        habit_id: habitId
      },
      actions: [
        { action: 'complete', title: '✅ Mark Done' },
        { action: 'snooze', title: '⏳ Snooze 1h' }
      ]
    };

    // Prefer Service Worker registration to route to Windows Action Center
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.ready.then(function (reg) {
        return reg.showNotification(title, options);
      }).catch(function () {
        fallbackNotification(title, options, url);
      });
    } else {
      fallbackNotification(title, options, url);
    }
  }

  function fallbackNotification(title, options, url) {
    try {
      var n = new Notification(title, options);
      n.onclick = function () {
        window.focus();
        window.location.href = url || '/habits/';
      };
    } catch (e) {
      console.warn('[HabitAlarm] Notification fallback failed:', e);
    }
  }

  // -------------------------------------------------------------------------
  // 4. In-App Floating Alarm Banner (Guaranteed visual fallback)
  // -------------------------------------------------------------------------
  function showFloatingAlarm(habit) {
    var container = document.getElementById('habit-alarm-toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'habit-alarm-toast-container';
      container.style.cssText = 'position: fixed; top: 1.25rem; right: 1.25rem; z-index: 999999; display: flex; flex-direction: column; gap: 0.75rem; max-width: 390px; width: 92%; pointer-events: none;';
      document.body.appendChild(container);
    }

    var existing = document.getElementById('alarm-toast-' + habit.id);
    if (existing) return;

    var toast = document.createElement('div');
    toast.id = 'alarm-toast-' + habit.id;
    toast.style.cssText = 'pointer-events: auto; background: var(--surface-raised, #1e293b); color: var(--text-main, #f8fafc); border: 2px solid #f59e0b; border-radius: 12px; padding: 1rem 1.15rem; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 0 15px rgba(245, 158, 11, 0.3); animation: habitAlarmSlideIn 0.3s ease; position: relative;';

    toast.innerHTML = [
      '<div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.4rem;">',
      '  <div style="display: flex; align-items: center; gap: 0.5rem;">',
      '    <span style="font-size: 1.25rem; animation: habitBellRing 1.5s infinite;">🔔</span>',
      '    <strong style="font-size: 0.95rem; color: #fbbf24;">Habit Alert &amp; Reminder</strong>',
      '  </div>',
      '  <button type="button" class="close-alarm-toast-btn" style="background: none; border: none; color: var(--text-muted, #94a3b8); font-size: 1.25rem; cursor: pointer; padding: 0 0.2rem; line-height: 1;">&times;</button>',
      '</div>',
      '<div style="font-size: 0.95rem; font-weight: 700; margin-bottom: 0.25rem;">' + escapeHtml(habit.name) + '</div>',
      '<p style="font-size: 0.8rem; color: var(--text-muted, #94a3b8); line-height: 1.4; margin: 0 0 0.75rem 0;">',
      '  This habit is open to be marked! Preserve your consistency streak and earn <strong>' + (habit.pixel_score || 2) + ' pixels</strong>.',
      '</p>',
      '<div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">',
      '  <button type="button" class="alarm-done-btn btn btn-sm btn-primary" style="font-size: 0.75rem; padding: 0.3rem 0.65rem; background: #10b981; border-color: #059669; font-weight: 700;">✅ Mark Done</button>',
      '  <button type="button" class="alarm-snooze-btn btn btn-sm btn-outline" style="font-size: 0.75rem; padding: 0.3rem 0.65rem;">⏳ Snooze 1h</button>',
      '  <button type="button" class="alarm-dismiss-btn btn btn-sm btn-ghost" style="font-size: 0.75rem; padding: 0.3rem 0.5rem;">Dismiss</button>',
      '</div>'
    ].join('');

    container.appendChild(toast);

    toast.querySelector('.close-alarm-toast-btn').onclick = function () { toast.remove(); };
    toast.querySelector('.alarm-dismiss-btn').onclick = function () { toast.remove(); };

    toast.querySelector('.alarm-done-btn').onclick = function () {
      fetch('/api/v1/habits/' + habit.id + '/complete/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCsrfToken(),
          'X-Requested-With': 'XMLHttpRequest'
        }
      }).then(function (r) { return r.json(); })
        .then(function (res) {
          toast.remove();
          if (res.success || res.status === 'success') {
            window.location.reload();
          }
        }).catch(function () {
          window.location.href = '/habits/' + habit.id + '/complete/';
        });
    };

    toast.querySelector('.alarm-snooze-btn').onclick = function () {
      fetch('/api/v1/habits/' + habit.id + '/reminder/snooze/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify({ minutes: 60 })
      }).then(function () {
        toast.remove();
      });
    };
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
  }

  // -------------------------------------------------------------------------
  // 5. Real-time Alarm Poller & Local Intimation Dispatcher
  // -------------------------------------------------------------------------
  function checkDueAlarms() {
    fetch('/api/v1/habits/reminders/active/', {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
      .then(function (r) {
        if (!r.ok) return null;
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.reminders || !Array.isArray(data.reminders)) return;

        var now = new Date();
        var nowTotalMins = now.getHours() * 60 + now.getMinutes();
        var todayDateStr = data.server_date || now.toISOString().slice(0, 10);
        var nowTs = Date.now();

        data.reminders.forEach(function (habit) {
          if (!habit.reminder_time) return;

          // Check if snoozed
          if (habit.snoozed_until) {
            var snoozeDate = new Date(habit.snoozed_until);
            if (snoozeDate > now) {
              return; // Still in snooze window
            }
          }

          var parts = habit.reminder_time.split(':');
          var remHours = parseInt(parts[0], 10);
          var remMins = parseInt(parts[1], 10);
          var remTotalMins = remHours * 60 + remMins;

          // Check if configured reminder time has arrived or passed
          if (nowTotalMins >= remTotalMins) {
            var habitStateKey = 'habitpulse_alarm_last_' + habit.id + '_' + todayDateStr;
            var lastAlerted = parseInt(localStorage.getItem(habitStateKey) || '0', 10);

            var shouldAlert = false;
            if (!lastAlerted) {
              // Not yet alerted today
              shouldAlert = true;
            } else if (habit.reminder_snooze_interval > 0) {
              // Repeat interval in minutes
              var intervalMs = habit.reminder_snooze_interval * 60 * 1000;
              if (nowTs - lastAlerted >= intervalMs) {
                shouldAlert = true;
              }
            }

            if (shouldAlert) {
              localStorage.setItem(habitStateKey, String(nowTs));
              triggerHabitAlarm(habit);
            }
          }
        });
      })
      .catch(function () {});
  }

  function triggerHabitAlarm(habit) {
    // 1. Play Web Audio chime
    playAlarmChime();

    // 2. Dispatch to Windows Notification Center / Action Center via Service Worker
    var title = '⏰ Habit Alert: ' + habit.name;
    var body = 'Time to complete your habit! Keep your streak and earn ' + (habit.pixel_score || 2) + ' pixels.';
    showSystemNotification(title, body, habit.id, '/habits/');

    // 3. Show in-app floating banner
    showFloatingAlarm(habit);
  }

  // -------------------------------------------------------------------------
  // 6. Alarm Configuration Modal Handler
  // -------------------------------------------------------------------------
  function initAlarmModal() {
    var modal = document.getElementById('habit-alarm-modal');
    if (!modal) return;

    var habitIdInput = document.getElementById('modal-alarm-habit-id');
    var habitNameEl = document.getElementById('modal-alarm-habit-name');
    var enabledInput = document.getElementById('modal-alarm-enabled');
    var timeInput = document.getElementById('modal-alarm-time');
    var snoozeSelect = document.getElementById('modal-alarm-snooze');
    var testStatusEl = document.getElementById('modal-alarm-test-status');
    var form = document.getElementById('habit-alarm-form');
    var testBtn = document.getElementById('modal-alarm-test-btn');
    var calSyncBtn = document.getElementById('modal-alarm-calendar-btn');
    var closeBtn = document.getElementById('modal-alarm-close-btn');
    var cancelBtn = document.getElementById('modal-alarm-cancel-btn');

    function closeModal() {
      modal.style.display = 'none';
      if (testStatusEl) testStatusEl.style.display = 'none';
    }

    if (closeBtn) closeBtn.onclick = closeModal;
    if (cancelBtn) cancelBtn.onclick = closeModal;

    // Delegate click on any .habit-alarm-btn across the page (Dashboard and Habits List)
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('.habit-alarm-btn');
      if (!btn) return;
      e.preventDefault();

      var habitId = btn.getAttribute('data-habit-id');
      var habitName = btn.getAttribute('data-habit-name') || 'Habit';
      var enabled = btn.getAttribute('data-enabled') === '1';
      var timeVal = btn.getAttribute('data-time') || '';
      var snoozeVal = btn.getAttribute('data-snooze') || '0';

      habitIdInput.value = habitId;
      habitNameEl.textContent = habitName;
      // Default alarm toggle to ON (true) when configuring
      enabledInput.checked = (btn.getAttribute('data-enabled') === '0') ? true : enabled;
      timeInput.value = timeVal || '08:00';
      snoozeSelect.value = snoozeVal;

      if (calSyncBtn) {
        calSyncBtn.href = '/habits/' + habitId + '/calendar.ics';
      }

      if (testStatusEl) {
        testStatusEl.style.display = 'none';
        testStatusEl.textContent = '';
      }

      modal.style.display = 'flex';
      getAudioContext(); // Pre-warm audio context on user gesture
    });

    // Test Audio & Notification Button
    if (testBtn) {
      testBtn.onclick = function () {
        var habitId = habitIdInput.value;
        var habitName = habitNameEl.textContent || 'Habit';

        playAlarmChime();
        showFloatingAlarm({ id: habitId, name: habitName, pixel_score: 2 });

        if ('Notification' in window && Notification.permission === 'denied') {
          if (testStatusEl) {
            testStatusEl.style.display = 'block';
            testStatusEl.style.background = 'rgba(239, 68, 68, 0.15)';
            testStatusEl.style.color = '#ef4444';
            testStatusEl.style.border = '1px solid rgba(239, 68, 68, 0.3)';
            testStatusEl.textContent = '⚠️ Desktop notifications blocked in browser settings. Click the lock/tune icon in your address bar and set Notifications to Allow.';
          }
        }

        // 1. Request notification permission if not yet decided
        var reqPromise = ('Notification' in window && Notification.permission === 'default')
          ? Notification.requestPermission()
          : Promise.resolve('Notification' in window ? Notification.permission : 'denied');

        reqPromise.then(function (perm) {
          if (perm === 'granted') {
            setupWebPushSubscription();
            showSystemNotification(
              '⏰ Test Alert: ' + habitName,
              'Windows and Phone notifications are working perfectly on HabitPulse!',
              habitId,
              '/habits/'
            );
          }

          // 2. Dispatch server test push to all connected devices (phones + laptop)
          if (testStatusEl) {
            testStatusEl.style.display = 'block';
            testStatusEl.style.background = 'rgba(245, 158, 11, 0.15)';
            testStatusEl.style.color = '#fbbf24';
            testStatusEl.style.border = '1px solid rgba(245, 158, 11, 0.3)';
            testStatusEl.textContent = '⏳ Dispatching test alert to your devices...';
          }

          fetch('/api/v1/habits/reminders/test-push/', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCsrfToken(),
              'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ habit_id: habitId })
          })
            .then(function (r) { return r.json(); })
            .then(function (res) {
              if (testStatusEl) {
                testStatusEl.style.display = 'block';
                testStatusEl.style.background = 'rgba(16, 185, 129, 0.15)';
                testStatusEl.style.color = '#10b981';
                testStatusEl.style.border = '1px solid rgba(16, 185, 129, 0.3)';
                testStatusEl.textContent = '✓ ' + (res.message || 'Test alert dispatched!');
              }
            })
            .catch(function () {
              if (testStatusEl) {
                testStatusEl.style.display = 'block';
                testStatusEl.style.background = 'rgba(59, 130, 246, 0.15)';
                testStatusEl.style.color = '#60a5fa';
                testStatusEl.style.border = '1px solid rgba(59, 130, 246, 0.3)';
                testStatusEl.textContent = '✓ Local audio & desktop alert triggered!';
              }
            });
        });
      };
    }

    // Submit form via AJAX
    if (form) {
      form.onsubmit = function (e) {
        e.preventDefault();
        var habitId = habitIdInput.value;
        if (!habitId) return;

        var payload = {
          reminder_enabled: enabledInput.checked,
          reminder_time: timeInput.value,
          reminder_snooze_interval: parseInt(snoozeSelect.value, 10) || 0
        };

        fetch('/api/v1/habits/' + habitId + '/reminder/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
            'X-Requested-With': 'XMLHttpRequest'
          },
          body: JSON.stringify(payload)
        })
          .then(function (r) {
            if (!r.ok) {
              return r.text().then(function (text) {
                var msg = 'Server returned ' + r.status;
                try {
                  var errJson = JSON.parse(text);
                  if (errJson.error || errJson.detail) msg = errJson.error || errJson.detail;
                } catch (e) {}
                throw new Error(msg);
              });
            }
            return r.json();
          })
          .then(function (res) {
            closeModal();
            // Update all button badges matching this habit (Dashboard and Habits list)
            var btns = document.querySelectorAll('.habit-alarm-btn[data-habit-id="' + habitId + '"]');
            btns.forEach(function (btn) {
              btn.setAttribute('data-enabled', res.reminder_enabled ? '1' : '0');
              btn.setAttribute('data-time', res.reminder_time || '');
              btn.setAttribute('data-snooze', payload.reminder_snooze_interval);
              if (res.reminder_enabled && res.reminder_display && res.reminder_display !== 'Off') {
                btn.innerHTML = '<span style="color: #f59e0b;">🔔</span> <span>' + escapeHtml(res.reminder_display) + '</span>';
                btn.classList.add('has-alarm');
                btn.style.borderColor = '#f59e0b';
                btn.style.color = '#fbbf24';
                btn.style.background = 'rgba(245, 158, 11, 0.08)';
              } else {
                btn.innerHTML = '<span style="opacity: 0.65;">🔔</span> <span>Alert</span>';
                btn.classList.remove('has-alarm');
                btn.style.borderColor = '';
                btn.style.color = '';
                btn.style.background = '';
              }
            });

            // Prompt permission if enabled and default
            if ('Notification' in window && Notification.permission === 'default' && payload.reminder_enabled) {
              Notification.requestPermission().then(function (perm) {
                if (perm === 'granted') {
                  setupWebPushSubscription();
                }
              });
            }
          })
          .catch(function (err) {
            alert('Failed to update alarm: ' + err);
          });
      };
    }
  }

  // -------------------------------------------------------------------------
  // 7. Request Notification Permission Prompt Banner (PWA & Desktop)
  // -------------------------------------------------------------------------
  function checkNotificationBanner() {
    if (!('Notification' in window) || Notification.permission !== 'default') {
      return;
    }

    if (localStorage.getItem('habitpulse_alarm_banner_dismissed')) {
      return;
    }

    var banner = document.getElementById('habit-notification-permission-banner');
    if (banner) {
      banner.style.display = 'block';
      var enableBtn = document.getElementById('enable-push-notifications-btn');
      var dismissBtn = document.getElementById('dismiss-push-notifications-btn');

      if (enableBtn) {
        enableBtn.onclick = function () {
          Notification.requestPermission().then(function (permission) {
            banner.style.display = 'none';
            if (permission === 'granted') {
              setupWebPushSubscription();
              playAlarmChime();
              showSystemNotification(
                '🔔 Habit Alerts Enabled',
                'You will now receive habit alerts directly in your Windows notification bar and on your phone!',
                null,
                '/habits/'
              );
            }
          });
        };
      }

      if (dismissBtn) {
        dismissBtn.onclick = function () {
          banner.style.display = 'none';
          localStorage.setItem('habitpulse_alarm_banner_dismissed', 'true');
        };
      }
    }
  }

  // -------------------------------------------------------------------------
  // 8. Initialization
  // -------------------------------------------------------------------------
  window.addEventListener('DOMContentLoaded', function () {
    initAlarmModal();
    checkNotificationBanner();
    setupWebPushSubscription();

    // Start background alarm polling immediately and then every 30 seconds
    checkDueAlarms();
    setInterval(checkDueAlarms, 30000);
  });

  // Export helpers for console or manual testing
  window.HabitPulseAlarm = {
    playChime: playAlarmChime,
    checkDueAlarms: checkDueAlarms,
    setupPush: setupWebPushSubscription,
    showNotification: showSystemNotification
  };
})();
