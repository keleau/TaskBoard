(function () {
    'use strict';

    var widget = document.getElementById('pomodoro');
    if (!widget) {
        return;
    }
    var STORAGE_KEY = 'taskboard.pomodoro.v1:' + (widget.getAttribute('data-user') || 'anonymous');
    var MODES = {
        focus: { label: '专注', seconds: 25 * 60, ring: '#6366f1' },
        short: { label: '短休息', seconds: 5 * 60, ring: '#10b981' },
        long: { label: '长休息', seconds: 15 * 60, ring: '#3b82f6' }
    };
    var RING_LENGTH = 2 * Math.PI * 52;

    var els = {
        panel: document.getElementById('pomodoroPanel'),
        close: widget.querySelector('[data-pomodoro-close]'),
        modes: Array.prototype.slice.call(widget.querySelectorAll('[data-pomodoro-mode]')),
        ring: document.getElementById('pomodoroRing'),
        time: document.getElementById('pomodoroTime'),
        state: document.getElementById('pomodoroState'),
        task: document.getElementById('pomodoroTask'),
        start: document.getElementById('pomodoroStart'),
        reset: document.getElementById('pomodoroReset'),
        count: document.getElementById('pomodoroCount'),
        minutes: document.getElementById('pomodoroMinutes'),
        fab: document.getElementById('pomodoroFab'),
        fabTime: document.getElementById('pomodoroFabTime')
    };

    var timerId = null;
    var audioCtx = null;
    var state = loadState();

    function pad(value) {
        return String(value).padStart(2, '0');
    }

    function dateKey() {
        var now = new Date();
        return now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate());
    }

    function defaultState() {
        return {
            mode: 'focus',
            remaining: MODES.focus.seconds,
            running: false,
            endAt: null,
            taskTitle: '',
            date: dateKey(),
            completed: 0,
            expired: false
        };
    }

    function clamp(value, min, max) {
        if (!isFinite(value)) {
            return min;
        }
        return Math.min(max, Math.max(min, value));
    }

    function loadState() {
        var fallback = defaultState();
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) {
                return fallback;
            }
            var data = JSON.parse(raw);
            var next = defaultState();
            next.mode = MODES[data.mode] ? data.mode : 'focus';
            next.completed = Math.max(0, parseInt(data.completed, 10) || 0);
            next.taskTitle = typeof data.taskTitle === 'string' ? data.taskTitle.slice(0, 100) : '';
            next.date = data.date === dateKey() ? data.date : dateKey();
            if (data.date !== dateKey()) {
                next.completed = 0;
            }
            next.remaining = clamp(Number(data.remaining), 0, MODES[next.mode].seconds);
            next.running = Boolean(data.running) && Number(data.endAt) > 0;
            next.endAt = next.running ? Number(data.endAt) : null;
            if (next.running) {
                var left = Math.ceil((next.endAt - Date.now()) / 1000);
                if (left > 0) {
                    next.remaining = Math.min(MODES[next.mode].seconds, left);
                } else {
                    next.remaining = 0;
                    next.expired = true;
                }
            }
            return next;
        } catch (error) {
            return fallback;
        }
    }

    function saveState() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify({
                mode: state.mode,
                remaining: state.remaining,
                running: state.running,
                endAt: state.endAt,
                taskTitle: state.taskTitle,
                date: state.date,
                completed: state.completed
            }));
        } catch (error) {
            /* 本地存储不可用时，计时仍然在当前页面内工作 */
        }
    }

    function formatTime(seconds) {
        var total = Math.max(0, Math.ceil(seconds));
        return pad(Math.floor(total / 60)) + ':' + pad(total % 60);
    }

    function render() {
        var mode = MODES[state.mode];
        var paused = !state.running && state.remaining > 0 && state.remaining < mode.seconds;
        widget.setAttribute('data-mode', state.mode);
        els.time.textContent = formatTime(state.remaining);

        if (state.running) {
            els.state.textContent = state.mode === 'focus' ? '专注中' : '休息中';
        } else if (state.remaining <= 0) {
            els.state.textContent = '已完成';
        } else if (paused) {
            els.state.textContent = '已暂停';
        } else {
            els.state.textContent = mode.label + '待开始';
        }

        if (state.taskTitle) {
            els.task.hidden = false;
            els.task.querySelector('span').textContent = state.taskTitle;
        } else {
            els.task.hidden = true;
        }

        els.start.querySelector('span').textContent = state.running
            ? '暂停'
            : (state.remaining > 0 && state.remaining < mode.seconds ? '继续' : '开始');
        els.start.querySelector('i').className = state.running ? 'fas fa-pause' : 'fas fa-play';
        els.count.textContent = state.completed;
        els.minutes.textContent = state.completed * 25;
        els.fabTime.textContent = formatTime(state.remaining);
        els.fab.classList.toggle('is-running', state.running);
        els.fab.classList.toggle('is-paused', paused);
        widget.classList.toggle('is-running', state.running);

        var progress = mode.seconds ? clamp(state.remaining / mode.seconds, 0, 1) : 0;
        els.ring.style.strokeDashoffset = String(RING_LENGTH * (1 - progress));
        els.ring.style.stroke = mode.ring;

        els.modes.forEach(function (button) {
            button.classList.toggle('is-active', button.getAttribute('data-pomodoro-mode') === state.mode);
        });
    }

    function stopTicker() {
        if (timerId) {
            window.clearInterval(timerId);
            timerId = null;
        }
    }

    function startTicker() {
        stopTicker();
        timerId = window.setInterval(tick, 500);
    }

    function tick() {
        if (!state.running) {
            return;
        }
        var left = Math.max(0, (state.endAt - Date.now()) / 1000);
        state.remaining = left;
        if (left <= 0) {
            completeSession();
            return;
        }
        render();
    }

    function ensureAudio() {
        try {
            var AudioCtor = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtor) {
                return;
            }
            if (!audioCtx) {
                audioCtx = new AudioCtor();
            }
            if (audioCtx.state === 'suspended') {
                audioCtx.resume();
            }
        } catch (error) {
            audioCtx = null;
        }
    }

    function playBeep() {
        try {
            ensureAudio();
            if (!audioCtx) {
                return;
            }
            var oscillator = audioCtx.createOscillator();
            var gain = audioCtx.createGain();
            oscillator.type = 'sine';
            oscillator.frequency.setValueAtTime(880, audioCtx.currentTime);
            gain.gain.setValueAtTime(0.0001, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.14, audioCtx.currentTime + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.9);
            oscillator.connect(gain);
            gain.connect(audioCtx.destination);
            oscillator.start();
            oscillator.stop(audioCtx.currentTime + 0.95);
        } catch (error) {
            /* 浏览器阻止自动播放时静默失败 */
        }
    }

    function notify(message, isError) {
        if (window.showAppToast) {
            window.showAppToast(message, isError);
        }
    }

    function setModeKeepTask(mode) {
        state.mode = mode;
        state.remaining = MODES[mode].seconds;
        state.running = false;
        state.endAt = null;
    }

    function completeSession() {
        stopTicker();
        var finishedMode = state.mode;
        state.running = false;
        state.endAt = null;
        state.remaining = 0;
        playBeep();

        if (state.date !== dateKey()) {
            state.date = dateKey();
            state.completed = 0;
        }

        if (finishedMode === 'focus') {
            state.completed += 1;
            setModeKeepTask(state.completed % 4 === 0 ? 'long' : 'short');
            notify('专注完成！今日已完成 ' + state.completed + ' 个番茄，休息一下。', false);
        } else {
            setModeKeepTask('focus');
            notify('休息结束，准备开始下一段专注。', false);
        }

        saveState();
        render();
    }

    function start() {
        if (state.running) {
            return;
        }
        if (state.remaining <= 0) {
            state.remaining = MODES[state.mode].seconds;
        }
        if (state.date !== dateKey()) {
            state.date = dateKey();
            state.completed = 0;
        }
        ensureAudio();
        state.running = true;
        state.endAt = Date.now() + state.remaining * 1000;
        saveState();
        startTicker();
        render();
    }

    function pause() {
        if (!state.running) {
            return;
        }
        state.remaining = Math.max(0, (state.endAt - Date.now()) / 1000);
        state.running = false;
        state.endAt = null;
        stopTicker();
        saveState();
        render();
    }

    function reset() {
        stopTicker();
        state.running = false;
        state.endAt = null;
        state.remaining = MODES[state.mode].seconds;
        saveState();
        render();
    }

    function switchMode(mode) {
        if (!MODES[mode] || mode === state.mode) {
            return;
        }
        if (state.running && !window.confirm('切换模式会结束当前计时，确定吗？')) {
            return;
        }
        stopTicker();
        state.running = false;
        state.endAt = null;
        state.mode = mode;
        state.remaining = MODES[mode].seconds;
        saveState();
        render();
    }

    function openPanel() {
        widget.classList.add('is-open');
        els.panel.setAttribute('aria-hidden', 'false');
        els.fab.setAttribute('aria-expanded', 'true');
    }

    function closePanel() {
        widget.classList.remove('is-open');
        els.panel.setAttribute('aria-hidden', 'true');
        els.fab.setAttribute('aria-expanded', 'false');
    }

    function focusOnTask(title) {
        title = String(title || '').trim().slice(0, 100);
        if (!title) {
            return;
        }

        var sameTask = state.mode === 'focus' && state.taskTitle === title;
        if (sameTask) {
            openPanel();
            if (!state.running) {
                start();
            }
            return;
        }

        if (state.running && !window.confirm('当前有一段计时正在进行，开始新的任务专注会结束它，确定吗？')) {
            openPanel();
            return;
        }

        stopTicker();
        state.mode = 'focus';
        state.taskTitle = title;
        state.remaining = MODES.focus.seconds;
        state.running = false;
        state.endAt = null;
        state.date = dateKey();
        openPanel();
        start();
    }

    window.startPomodoroForTask = focusOnTask;

    els.ring.style.strokeDasharray = String(RING_LENGTH);
    els.start.addEventListener('click', function () {
        if (state.running) {
            pause();
        } else {
            start();
        }
    });
    els.reset.addEventListener('click', reset);
    els.fab.addEventListener('click', function () {
        if (widget.classList.contains('is-open')) {
            closePanel();
        } else {
            openPanel();
        }
    });
    els.close.addEventListener('click', closePanel);
    els.modes.forEach(function (button) {
        button.addEventListener('click', function () {
            switchMode(button.getAttribute('data-pomodoro-mode'));
        });
    });
    document.addEventListener('click', function (event) {
        var trigger = event.target.closest('[data-focus-task]');
        if (!trigger) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        focusOnTask(trigger.getAttribute('data-focus-task'));
    });
    document.addEventListener('visibilitychange', function () {
        if (document.hidden || !state.running) {
            return;
        }
        var left = Math.max(0, (state.endAt - Date.now()) / 1000);
        state.remaining = left;
        if (left <= 0) {
            completeSession();
        } else {
            render();
        }
    });

    render();
    if (state.expired) {
        state.expired = false;
        state.running = true;
        completeSession();
    } else if (state.running) {
        startTicker();
    }
    saveState();
})();
