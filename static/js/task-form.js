/* 任务表单：新增/编辑弹窗与子任务编辑器 */
(function () {
    'use strict';

    function createSubtaskRow(container, data) {
        data = data || {};
        var row = document.createElement('div');
        row.className = 'subtask-row';

        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'form-check-input subtask-done';
        checkbox.checked = Boolean(data.is_done);

        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'form-control form-control-sm subtask-content';
        input.maxLength = 100;
        input.placeholder = '子任务内容';
        input.value = data.content || '';
        input.addEventListener('keydown', function (event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                var nextRow = createSubtaskRow(container);
                nextRow.querySelector('.subtask-content').focus();
            }
        });

        var remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'subtask-remove';
        remove.title = '移除子任务';
        remove.innerHTML = '<i class="fas fa-xmark"></i>';

        row.appendChild(checkbox);
        row.appendChild(input);
        row.appendChild(remove);
        container.appendChild(row);
        return row;
    }

    function setSubtaskRows(container, items) {
        container.innerHTML = '';
        items.forEach(function (item) {
            createSubtaskRow(container, item);
        });
        if (!container.children.length) {
            createSubtaskRow(container);
        }
    }

    function serializeSubtasks(form) {
        var editor = form.querySelector('.subtask-editor');
        var hidden = form.querySelector('input[name="subtasks"]');
        if (!editor || !hidden) {
            return;
        }
        var items = [];
        editor.querySelectorAll('.subtask-row').forEach(function (row) {
            var input = row.querySelector('.subtask-content');
            var content = input.value.trim();
            if (!content) {
                return;
            }
            items.push({
                content: content,
                is_done: row.querySelector('.subtask-done').checked
            });
        });
        hidden.value = JSON.stringify(items);
    }

    document.querySelectorAll('.subtask-editor').forEach(function (editor) {
        editor.addEventListener('click', function (event) {
            var button = event.target.closest('.subtask-remove');
            if (button) {
                button.closest('.subtask-row').remove();
            }
        });
    });

    document.querySelectorAll('.js-add-subtask').forEach(function (button) {
        button.addEventListener('click', function () {
            var form = button.closest('form');
            if (!form) {
                return;
            }
            var editor = form.querySelector('.subtask-editor');
            var row = createSubtaskRow(editor);
            row.querySelector('.subtask-content').focus();
        });
    });

    var createModal = document.getElementById('createTaskModal');
    if (createModal) {
        createModal.addEventListener('show.bs.modal', function () {
            var editor = document.getElementById('createSubtasks');
            if (editor && !editor.children.length) {
                createSubtaskRow(editor);
            }
        });
    }

    var editModal = document.getElementById('editTaskModal');
    if (editModal) {
        editModal.addEventListener('show.bs.modal', function (event) {
            var trigger = event.relatedTarget;
            if (!trigger) {
                return;
            }
            var card = trigger.closest('.task-card');
            if (!card) {
                return;
            }
            var form = document.getElementById('editTaskForm');
            form.setAttribute('action', card.getAttribute('data-edit-url') || '');
            document.getElementById('editTaskIdLabel').textContent = '#' + card.getAttribute('data-task-id');
            document.getElementById('editTaskTitle').value = card.getAttribute('data-title') || '';
            document.getElementById('editTaskContent').value = card.getAttribute('data-content') || '';
            document.getElementById('editPriority').value = card.getAttribute('data-priority') || '1';
            document.getElementById('editTags').value = card.getAttribute('data-tags') || '';
            document.getElementById('editDeadline').value = card.getAttribute('data-deadline') || '';

            var subtasks = [];
            try {
                subtasks = JSON.parse(card.getAttribute('data-subtasks') || '[]');
            } catch (error) {
                subtasks = [];
            }
            setSubtaskRows(document.getElementById('editSubtasks'), subtasks);
        });
        editModal.addEventListener('shown.bs.modal', function () {
            document.getElementById('editTaskTitle').focus();
        });
    }

    document.querySelectorAll('#createTaskModal form, #editTaskForm').forEach(function (form) {
        form.addEventListener('submit', function () {
            serializeSubtasks(form);
        });
    });

    var params = new URLSearchParams(window.location.search);
    var editId = params.get('edit');
    if (editId && /^\d+$/.test(editId)) {
        var card = document.querySelector('.task-card[data-task-id="' + editId + '"]');
        if (card) {
            var editButton = card.querySelector('[data-bs-target="#editTaskModal"]');
            if (editButton) {
                editButton.click();
            }
            params.delete('edit');
            var query = params.toString();
            window.history.replaceState({}, '', window.location.pathname + (query ? '?' + query : ''));
        }
    }
})();
