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

    function showToast(message, isError) {
        if (window.showAppToast) {
            window.showAppToast(message, isError);
        }
    }

    function updateCounts(counts) {
        if (!counts) {
            return;
        }
        Object.keys(counts).forEach(function (columnId) {
            var badge = document.querySelector('.column-count[data-count-id="' + columnId + '"]');
            if (badge) {
                badge.textContent = counts[columnId];
            }
        });
    }

    function updateUrgentCount(count) {
        var chip = document.querySelector('[data-urgent-chip]');
        if (!chip || typeof count !== 'number') {
            return;
        }
        var value = chip.querySelector('strong');
        if (value) {
            value.textContent = count;
        }
        chip.classList.toggle('is-alert', count > 0);
    }

    function updateTotalCount(count) {
        var value = document.querySelector('[data-total-count]');
        if (value && typeof count === 'number') {
            value.textContent = count;
        }
    }

    function updateTrashCount(count) {
        if (typeof count !== 'number') {
            return;
        }
        var dropCount = document.querySelector('.board-trash-count');
        if (dropCount) {
            dropCount.textContent = count;
            dropCount.hidden = count === 0;
        }
        var dropzone = document.querySelector('[data-trash-dropzone]');
        if (dropzone) {
            dropzone.setAttribute('data-trash-count', String(count));
        }
    }

    function showUndoToast(taskId) {
        var stack = document.getElementById('toastStack');
        if (!stack || !window.bootstrap) {
            return;
        }
        var wrapper = document.createElement('div');
        wrapper.className = 'toast align-items-center border-0 toast-success';
        wrapper.setAttribute('role', 'alert');
        wrapper.innerHTML =
            '<div class="d-flex align-items-center">' +
                '<div class="toast-body"><i class="fas fa-trash-can me-2"></i>任务已移入垃圾桶</div>' +
                '<button type="button" class="toast-undo">撤销</button>' +
                '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="关闭"></button>' +
            '</div>';
        stack.appendChild(wrapper);
        wrapper.addEventListener('hidden.bs.toast', function () {
            wrapper.remove();
        });
        var undo = wrapper.querySelector('.toast-undo');
        undo.addEventListener('click', function () {
            undo.disabled = true;
            fetch('/task/' + taskId + '/restore', {
                method: 'POST',
                credentials: 'same-origin'
            }).then(function () {
                window.location.reload();
            }).catch(function () {
                window.location.reload();
            });
        });
        new bootstrap.Toast(wrapper, { delay: 5000 }).show();
    }

    function deleteTaskViaTrash(taskId) {
        if (!taskId) {
            return;
        }
        var filterActive = document.querySelector('.board-grid').getAttribute('data-filter-active') === '1';
        $.ajax({
            url: '/task/' + taskId + '/trash',
            type: 'POST',
            dataType: 'json'
        }).done(function (response) {
            if (response && response.code === 200) {
                updateCounts(response.counts);
                updateUrgentCount(response.urgent_count);
                updateTotalCount(response.total_count);
                updateTrashCount(response.trash_count);
                toggleEmptyStates();
                var dropzone = document.querySelector('[data-trash-dropzone]');
                if (dropzone) {
                    dropzone.classList.add('is-receiving');
                    window.setTimeout(function () {
                        dropzone.classList.remove('is-receiving');
                    }, 450);
                }
                if (filterActive) {
                    showToast(response.msg || '任务已移入垃圾桶', false);
                    window.setTimeout(function () { window.location.reload(); }, 650);
                } else {
                    showUndoToast(taskId);
                }
            } else {
                showToast((response && response.msg) || '删除失败', true);
                window.setTimeout(function () { window.location.reload(); }, 900);
            }
        }).fail(function (xhr) {
            if (xhr.status === 401) {
                window.location.href = '/login';
                return;
            }
            var message = (xhr.responseJSON && xhr.responseJSON.msg) || '删除失败，请刷新后重试';
            showToast(message, true);
            window.setTimeout(function () { window.location.reload(); }, 900);
        });
    }

    function toggleEmptyStates() {
        document.querySelectorAll('.task-list').forEach(function (list) {
            var hint = list.querySelector('.empty-hint');
            if (hint) {
                hint.classList.toggle('d-none', Boolean(list.querySelector('.task-card')));
            }
        });
    }

    function applyUrgency(card, response) {
        var urgent = Boolean(response.urgent);
        card.classList.toggle('task-urgent', urgent);
        var flags = card.querySelector('.task-flags');
        var badge = card.querySelector('.badge-urgent');
        if (urgent) {
            if (!badge && flags) {
                badge = document.createElement('span');
                badge.className = 'badge-urgent';
                flags.appendChild(badge);
            }
            if (badge) {
                badge.innerHTML = '<i class="fas fa-circle-exclamation"></i>' +
                    escapeHtml(response.deadline_label || '即将到期');
            }
        } else if (badge) {
            badge.remove();
        }
    }

    function applyFinishTime(card, response) {
        var meta = card.querySelector('.task-meta');
        if (!meta) {
            return;
        }
        var finish = card.querySelector('.task-finish');
        if (response.finish_time) {
            if (!finish) {
                finish = document.createElement('span');
                finish.className = 'task-finish';
                meta.insertBefore(finish, meta.querySelector('.task-owner'));
            }
            finish.innerHTML = '<i class="fas fa-circle-check"></i>' + escapeHtml(response.finish_time) + ' 完成';
        } else if (finish) {
            finish.remove();
        }
    }

    function moveTask(card, targetList) {
        var order = Array.from(targetList.querySelectorAll('.task-card'))
            .map(function (item) { return item.getAttribute('data-task-id'); })
            .join(',');
        var filterActive = document.querySelector('.board-grid').getAttribute('data-filter-active') === '1';

        $.ajax({
            url: '/task/move',
            type: 'POST',
            dataType: 'json',
            data: {
                task_id: card.getAttribute('data-task-id'),
                column_id: targetList.getAttribute('data-column-id'),
                order: order
            }
        }).done(function (response) {
            if (response && response.code === 200) {
                updateCounts(response.counts);
                updateUrgentCount(response.urgent_count);
                applyUrgency(card, response);
                applyFinishTime(card, response);
                toggleEmptyStates();
                showToast(response.msg || '状态更新成功', false);
                if (filterActive) {
                    window.setTimeout(function () { window.location.reload(); }, 650);
                }
            } else {
                showToast((response && response.msg) || '状态更新失败', true);
                window.setTimeout(function () { window.location.reload(); }, 900);
            }
        }).fail(function (xhr) {
            if (xhr.status === 401) {
                window.location.href = '/login';
                return;
            }
            var message = (xhr.responseJSON && xhr.responseJSON.msg) || '状态更新失败，请刷新后重试';
            showToast(message, true);
            window.setTimeout(function () { window.location.reload(); }, 900);
        });
    }

    document.querySelectorAll('.task-list').forEach(function (list) {
        Sortable.create(list, {
            group: 'task-board',
            animation: 180,
            easing: 'cubic-bezier(.2, .8, .2, 1)',
            draggable: '.task-card',
            filter: '.js-no-drag, a, button, input, textarea',
            ghostClass: 'task-ghost',
            chosenClass: 'task-chosen',
            dragClass: 'task-dragging',
            fallbackOnBody: true,
            swapThreshold: 0.65,
            onStart: function () {
                document.body.classList.add('is-task-dragging');
            },
            onEnd: function (event) {
                document.body.classList.remove('is-task-dragging');
                if (event.to.hasAttribute('data-trash-dropzone')) {
                    return;
                }
                moveTask(event.item, event.to);
            }
        });
    });

    var trashDropzone = document.querySelector('[data-trash-dropzone]');
    if (trashDropzone) {
        Sortable.create(trashDropzone, {
            group: { name: 'task-board', pull: false, put: true },
            sort: false,
            draggable: '.task-card',
            animation: 150,
            onAdd: function (event) {
                var card = event.item;
                var taskId = card.getAttribute('data-task-id');
                card.remove();
                document.body.classList.remove('is-task-dragging');
                deleteTaskViaTrash(taskId);
            }
        });
    }

    document.querySelectorAll('.js-filter-select').forEach(function (select) {
        select.addEventListener('change', function () {
            if (select.form) {
                select.form.submit();
            }
        });
    });

    var COLLAPSE_KEY = 'taskboard.collapsedColumns';

    function readCollapsedColumns() {
        try {
            var ids = JSON.parse(localStorage.getItem(COLLAPSE_KEY) || '[]');
            return Array.isArray(ids) ? ids.map(String) : [];
        } catch (error) {
            return [];
        }
    }

    function saveCollapsedColumns(ids) {
        try {
            localStorage.setItem(COLLAPSE_KEY, JSON.stringify(ids));
        } catch (error) {
            /* 本地存储不可用时仅当前页面生效 */
        }
    }

    function setColumnCollapsed(column, collapsed) {
        column.classList.toggle('is-collapsed', collapsed);
        var toggle = column.querySelector('[data-column-toggle]');
        if (toggle) {
            toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        }
    }

    function updateCollapseAllButton() {
        var button = document.getElementById('toggleAllColumns');
        if (!button) {
            return;
        }
        var columns = Array.prototype.slice.call(document.querySelectorAll('.board-column'));
        var collapsedCount = columns.filter(function (column) {
            return column.classList.contains('is-collapsed');
        }).length;
        var allCollapsed = columns.length > 0 && collapsedCount === columns.length;
        button.querySelector('span').textContent = allCollapsed ? '展开栏目' : '收起栏目';
        var icon = button.querySelector('i');
        if (icon) {
            icon.className = (allCollapsed ? 'fas fa-expand-arrows-alt' : 'fas fa-compress-arrows-alt') + ' me-1';
        }
    }

    function applyCollapsedColumns() {
        var ids = readCollapsedColumns();
        document.querySelectorAll('.board-column').forEach(function (column) {
            var id = column.getAttribute('data-column-id');
            setColumnCollapsed(column, ids.indexOf(id) !== -1);
        });
        updateCollapseAllButton();
    }

    applyCollapsedColumns();

    document.querySelectorAll('[data-column-toggle]').forEach(function (button) {
        button.addEventListener('click', function () {
            var column = button.closest('.board-column');
            if (!column) {
                return;
            }
            var willCollapse = !column.classList.contains('is-collapsed');
            setColumnCollapsed(column, willCollapse);
            var ids = readCollapsedColumns();
            var id = column.getAttribute('data-column-id');
            var index = ids.indexOf(id);
            if (willCollapse && index === -1) {
                ids.push(id);
            }
            if (!willCollapse && index !== -1) {
                ids.splice(index, 1);
            }
            saveCollapsedColumns(ids);
            updateCollapseAllButton();
        });
    });

    var collapseAllButton = document.getElementById('toggleAllColumns');
    if (collapseAllButton) {
        collapseAllButton.addEventListener('click', function () {
            var columns = Array.prototype.slice.call(document.querySelectorAll('.board-column'));
            var allCollapsed = columns.length > 0 && columns.every(function (column) {
                return column.classList.contains('is-collapsed');
            });
            var ids = [];
            columns.forEach(function (column) {
                setColumnCollapsed(column, !allCollapsed);
                if (!allCollapsed) {
                    ids.push(column.getAttribute('data-column-id'));
                }
            });
            saveCollapsedColumns(ids);
            updateCollapseAllButton();
        });
    }

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
            document.getElementById('editTaskDeadline').value = card.getAttribute('data-deadline') || '';

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
