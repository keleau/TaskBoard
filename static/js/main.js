(function () {
    'use strict';

    function escapeHtml(value) {
        return String(value).replace(/[&<>"']/g, function (ch) {
            return {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;'
            }[ch];
        });
    }

    window.showAppToast = function (message, isError) {
        var stack = document.getElementById('toastStack');
        if (!stack || !window.bootstrap) {
            return;
        }
        var wrapper = document.createElement('div');
        wrapper.className = 'toast align-items-center border-0 ' + (isError ? 'toast-error' : 'toast-success');
        wrapper.setAttribute('role', 'alert');
        wrapper.innerHTML =
            '<div class="d-flex">' +
                '<div class="toast-body"><i class="fas ' + (isError ? 'fa-circle-exclamation' : 'fa-circle-check') + ' me-2"></i>' +
                    escapeHtml(message) +
                '</div>' +
                '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="关闭"></button>' +
            '</div>';
        stack.appendChild(wrapper);
        wrapper.addEventListener('hidden.bs.toast', function () {
            wrapper.remove();
        });
        new bootstrap.Toast(wrapper, { delay: 2400 }).show();
    };

    document.addEventListener('DOMContentLoaded', function () {
        var alerts = document.querySelectorAll('.flash-stack .alert');
        alerts.forEach(function (alertEl) {
            window.setTimeout(function () {
                if (window.bootstrap) {
                    window.bootstrap.Alert.getOrCreateInstance(alertEl).close();
                }
            }, 4500);
        });
    });
})();
