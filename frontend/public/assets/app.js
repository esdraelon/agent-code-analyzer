(() => {
    const escapeHtml = (value) => String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');

    const flash = (message, kind = '') => {
        const element = document.getElementById('async-flash');
        if (!element) {
            return;
        }
        if (!message) {
            element.hidden = true;
            element.textContent = '';
            element.className = 'banner';
            return;
        }
        element.hidden = false;
        element.textContent = message;
        element.className = kind === 'error' ? 'banner error' : 'banner';
    };

    const apiRequest = async (path, options = {}) => {
        const method = (options.method || 'GET').toUpperCase();
        const headers = new Headers(options.headers || {});
        headers.set('Accept', 'application/json');
        let body = options.body;
        if (body !== undefined && body !== null && method !== 'GET' && method !== 'HEAD') {
            headers.set('Content-Type', 'application/json');
            body = typeof body === 'string' ? body : JSON.stringify(body);
        } else {
            body = undefined;
        }

        const response = await fetch(path, {
            method,
            headers,
            body,
        });

        const contentType = response.headers.get('content-type') || '';
        let payload = null;
        if (contentType.includes('application/json')) {
            payload = await response.json();
        } else {
            payload = { raw: await response.text() };
        }

        if (!response.ok || (payload && payload.ok === false)) {
            throw new Error((payload && (payload.error || payload.message)) || `Request failed (${response.status})`);
        }

        return { status: response.status, payload };
    };

    const projectEndpointName = (endpoint) => {
        const match = String(endpoint).match(/\/api\/projects\/([^/]+)(?:\/|$)/);
        return match ? decodeURIComponent(match[1]) : '';
    };

    const renderProjectCards = (projects) => {
        const list = document.getElementById('projects-list');
        const counter = document.getElementById('projects-count');
        const status = document.getElementById('projects-status');
        if (!list || !counter || !status) {
            return;
        }

        const items = Array.isArray(projects) ? projects : [];
        counter.textContent = `${items.length} project${items.length === 1 ? '' : 's'}`;
        if (items.length === 0) {
            status.textContent = 'No projects are registered yet.';
            list.replaceChildren();
            return;
        }

        status.textContent = 'Loaded.';
        list.innerHTML = items.map((project) => {
            const name = String(project.name || '');
            const encodedName = encodeURIComponent(name);
            const rootPath = escapeHtml(project.root_path || '');
            const description = String(project.description || '');
            const statusText = escapeHtml(project.status || 'idle');
            return `
                <article class="list-item">
                    <div class="topbar" style="margin-bottom:0; align-items:flex-start;">
                        <div>
                            <h3 style="margin-bottom:6px;"><a href="/projects/${encodedName}">${escapeHtml(name)}</a></h3>
                            <div class="muted">${rootPath}</div>
                        </div>
                        <span class="pill">${statusText}</span>
                    </div>
                    <div class="kv" style="margin-top:14px;">
                        <div><strong>Mode:</strong> ${escapeHtml(project.mode || '')}</div>
                        <div><strong>Indexed:</strong> ${escapeHtml(project.indexed_at || '—')}</div>
                        <div><strong>Files:</strong> ${escapeHtml(project.file_count ?? 0)}</div>
                        <div><strong>Symbols:</strong> ${escapeHtml(project.symbol_count ?? 0)}</div>
                    </div>
                    ${description ? `<p class="muted" style="margin-bottom:0;">${escapeHtml(description)}</p>` : ''}
                    <div class="actions">
                        <a class="button secondary" href="/projects/${encodedName}">Open</a>
                        <form method="post" action="/projects/${encodedName}/reingest" data-async-endpoint="/api/projects/${encodedName}/reingest" data-async-method="POST" data-async-project="${escapeHtml(name)}">
                            <input type="hidden" name="mode" value="refresh">
                            <input type="hidden" name="refresh" value="true">
                            <button type="submit">Reingest</button>
                        </form>
                        <form method="post" action="/projects/${encodedName}/offboard" data-async-endpoint="/api/projects/${encodedName}" data-async-method="DELETE" data-async-project="${escapeHtml(name)}" onsubmit="return confirm('Remove this project and its indexes?');">
                            <button type="submit" class="danger">Offboard</button>
                        </form>
                    </div>
                </article>
            `;
        }).join('');
    };

    const renderBreakdown = (element, items) => {
        if (!element) {
            return;
        }
        const rows = Array.isArray(items) ? items : [];
        if (rows.length === 0) {
            element.innerHTML = '<p class="muted" style="margin-top:10px;">No entries yet.</p>';
            return;
        }
        element.innerHTML = `<ul class="breakdown-list">${rows.map((item) => {
            const label = escapeHtml(item.label || item.key || '');
            const count = escapeHtml(item.count ?? 0);
            return `<li><span class="label">${label}</span><span class="count">${count}</span></li>`;
        }).join('')}</ul>`;
    };

    const renderProjectStatus = (project) => {
        const rootPath = document.getElementById('project-root-path');
        const status = document.getElementById('project-status');
        const mode = document.getElementById('project-mode');
        const created = document.getElementById('project-created');
        const updated = document.getElementById('project-updated');
        const indexed = document.getElementById('project-indexed');
        const files = document.getElementById('project-files');
        const symbols = document.getElementById('project-symbols');
        const description = document.getElementById('project-description');
        const overview = document.getElementById('project-index-overview');
        const hardBreakdown = document.getElementById('project-hard-breakdown');
        const softBreakdown = document.getElementById('project-soft-breakdown');
        if (!rootPath || !status || !mode || !created || !updated || !indexed || !files || !symbols || !description || !overview) {
            return;
        }

        rootPath.textContent = project.root_path || '—';
        status.textContent = project.status || 'idle';
        mode.textContent = project.mode || '—';
        created.textContent = project.created_at || '—';
        updated.textContent = project.updated_at || '—';
        indexed.textContent = project.indexed_at || '—';
        files.textContent = project.file_count ?? 0;
        symbols.textContent = project.symbol_count ?? 0;
        description.textContent = project.description || 'No description provided.';

        const summary = project.index_summary || {};
        const hard = summary.hard_total ?? project.file_count ?? 0;
        const soft = summary.soft_total ?? 0;
        const lexical = summary.lexical_total ?? 0;
        const semantic = summary.semantic_total ?? 0;

        overview.innerHTML = `
            <div>
                <span class="detail-label">Hard entries</span>
                <strong>${escapeHtml(hard)}</strong>
                <div class="muted">Lexical / AST-backed entries</div>
            </div>
            <div>
                <span class="detail-label">Soft entries</span>
                <strong>${escapeHtml(soft)}</strong>
                <div class="muted">Semantic / model-backed entries</div>
            </div>
            <div>
                <span class="detail-label">Lexical docs</span>
                <strong>${escapeHtml(lexical)}</strong>
                <div class="muted">Hard tree-sitter documents</div>
            </div>
            <div>
                <span class="detail-label">Semantic points</span>
                <strong>${escapeHtml(semantic)}</strong>
                <div class="muted">Soft Qdrant entries</div>
            </div>
        `;

        if (hardBreakdown) {
            hardBreakdown.innerHTML = `
                <div>
                    <span class="detail-label">Tree-sitter symbol types</span>
                    ${Array.isArray(summary.hard?.symbol_type_counts) && summary.hard.symbol_type_counts.length
                        ? `<ul class="breakdown-list">${summary.hard.symbol_type_counts.map((item) => `<li><span class="label">${escapeHtml(item.label || item.key || '')}</span><span class="count">${escapeHtml(item.count ?? 0)}</span></li>`).join('')}</ul>`
                        : '<p class="muted" style="margin-top:10px;">No entries yet.</p>'}
                </div>
                <div>
                    <span class="detail-label">Lexical document scopes</span>
                    ${Array.isArray(summary.hard?.lexical_scope_counts) && summary.hard.lexical_scope_counts.length
                        ? `<ul class="breakdown-list">${summary.hard.lexical_scope_counts.map((item) => `<li><span class="label">${escapeHtml(item.label || item.key || '')}</span><span class="count">${escapeHtml(item.count ?? 0)}</span></li>`).join('')}</ul>`
                        : '<p class="muted" style="margin-top:10px;">No entries yet.</p>'}
                </div>
                <div>
                    <span class="detail-label">Lexical symbol unit types</span>
                    ${Array.isArray(summary.hard?.lexical_symbol_unit_counts) && summary.hard.lexical_symbol_unit_counts.length
                        ? `<ul class="breakdown-list">${summary.hard.lexical_symbol_unit_counts.map((item) => `<li><span class="label">${escapeHtml(item.label || item.key || '')}</span><span class="count">${escapeHtml(item.count ?? 0)}</span></li>`).join('')}</ul>`
                        : '<p class="muted" style="margin-top:10px;">No entries yet.</p>'}
                </div>
            `;
        }

        if (softBreakdown) {
            softBreakdown.innerHTML = `
                <div>
                    <span class="detail-label">Semantic source kinds</span>
                    ${Array.isArray(summary.soft?.source_kind_counts) && summary.soft.source_kind_counts.length
                        ? `<ul class="breakdown-list">${summary.soft.source_kind_counts.map((item) => `<li><span class="label">${escapeHtml(item.label || item.key || '')}</span><span class="count">${escapeHtml(item.count ?? 0)}</span></li>`).join('')}</ul>`
                        : '<p class="muted" style="margin-top:10px;">No entries yet.</p>'}
                </div>
                <div>
                    <span class="detail-label">Semantic unit types</span>
                    ${Array.isArray(summary.soft?.unit_type_counts) && summary.soft.unit_type_counts.length
                        ? `<ul class="breakdown-list">${summary.soft.unit_type_counts.map((item) => `<li><span class="label">${escapeHtml(item.label || item.key || '')}</span><span class="count">${escapeHtml(item.count ?? 0)}</span></li>`).join('')}</ul>`
                        : '<p class="muted" style="margin-top:10px;">No entries yet.</p>'}
                </div>
            `;
        }
    };

    const renderJobs = (jobs, targetSelector = '#project-jobs', counterSelector = null) => {
        const target = document.querySelector(targetSelector);
        if (!target) {
            return;
        }
        const items = Array.isArray(jobs) ? jobs : [];
        if (counterSelector) {
            const counter = document.querySelector(counterSelector);
            if (counter) {
                counter.textContent = `${items.length} job${items.length === 1 ? '' : 's'}`;
            }
        }
        if (items.length === 0) {
            target.innerHTML = '<p class="muted">No job records are available yet.</p>';
            return;
        }

        target.innerHTML = `<div class="list">${items.map((job) => {
            const projectName = escapeHtml(job.project || '');
            const encodedProject = encodeURIComponent(job.project || '');
            const status = escapeHtml(job.status || '');
            return `
                <article class="list-item">
                    <div class="topbar" style="margin-bottom:0; align-items:flex-start;">
                        <div>
                            <strong>${projectName}</strong>
                            <div class="muted">Job ${escapeHtml(job.job_id || '')} · ${escapeHtml(job.action || '')} · ${escapeHtml(job.phase || '')}</div>
                        </div>
                        <span class="pill">${status}</span>
                    </div>
                    <div class="kv" style="margin-top:12px;">
                        <div><strong>Queued:</strong> ${escapeHtml(job.queued_at || '—')}</div>
                        <div><strong>Started:</strong> ${escapeHtml(job.started_at || '—')}</div>
                        <div><strong>Updated:</strong> ${escapeHtml(job.updated_at || '—')}</div>
                        <div><strong>Completed:</strong> ${escapeHtml(job.completed_at || '—')}</div>
                    </div>
                    <div class="pills" style="margin-top:12px;">
                        <a class="pill" href="/projects/${encodedProject}">Open project</a>
                        <a class="pill" href="/search?mode=unified&project=${encodedProject}">Search project</a>
                    </div>
                    ${job.last_error ? `<p class="banner error" style="margin-top:12px;">${escapeHtml(job.last_error)}</p>` : ''}
                </article>
            `;
        }).join('')}</div>`;
    };

    const loadProjectsPage = async () => {
        const list = document.getElementById('projects-list');
        if (!list) {
            return;
        }
        try {
            const { payload } = await apiRequest('/api/projects');
            renderProjectCards(payload.projects || []);
        } catch (error) {
            const status = document.getElementById('projects-status');
            if (status) {
                status.textContent = error.message;
            }
            flash(error.message, 'error');
        }
    };

    const loadProjectPage = async () => {
        const shell = document.querySelector('[data-project-name]');
        if (!shell) {
            return;
        }
        const projectName = shell.getAttribute('data-project-name') || '';
        if (!projectName) {
            return;
        }

        try {
            const [statusResult, jobsResult] = await Promise.all([
                apiRequest(`/api/projects/${encodeURIComponent(projectName)}/status`),
                apiRequest(`/api/projects/${encodeURIComponent(projectName)}/jobs`),
            ]);
            renderProjectStatus(statusResult.payload.project || {});
            renderJobs(jobsResult.payload.jobs || [], '#project-jobs');
        } catch (error) {
            const target = document.getElementById('project-jobs');
            if (target) {
                target.innerHTML = `<p class="banner error">${escapeHtml(error.message)}</p>`;
            }
            flash(error.message, 'error');
        }
    };

    const loadLogsPage = async () => {
        const select = document.getElementById('logs-project-select');
        const jobsTarget = document.getElementById('logs-jobs');
        const count = document.getElementById('logs-job-count');
        if (!select || !jobsTarget || !count) {
            return;
        }
        const selectedProject = new URLSearchParams(window.location.search).get('project') || '';
        try {
            const { payload } = await apiRequest(`/api/logs?project=${encodeURIComponent(selectedProject)}`);
            const projects = Array.isArray(payload.projects) ? payload.projects : [];
            select.innerHTML = [`<option value="">All projects</option>`]
                .concat(projects.map((project) => {
                    const name = String(project.name || '');
                    const selected = name === selectedProject ? ' selected' : '';
                    return `<option value="${escapeHtml(name)}"${selected}>${escapeHtml(name)}</option>`;
                }))
                .join('');
            renderJobs(payload.jobs || [], '#logs-jobs', '#logs-job-count');
            count.textContent = `${Array.isArray(payload.jobs) ? payload.jobs.length : 0} job${Array.isArray(payload.jobs) && payload.jobs.length === 1 ? '' : 's'}`;
        } catch (error) {
            jobsTarget.innerHTML = `<p class="banner error">${escapeHtml(error.message)}</p>`;
            flash(error.message, 'error');
        }
    };

    const handleAsyncForm = async (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || !form.matches('[data-async-endpoint]')) {
            return;
        }
        event.preventDefault();
        const endpoint = form.getAttribute('data-async-endpoint') || '';
        const method = (form.getAttribute('data-async-method') || form.method || 'POST').toUpperCase();
        const body = Object.fromEntries(new FormData(form).entries());
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.setAttribute('disabled', 'disabled');
        }

        try {
            const { status, payload } = await apiRequest(endpoint, {
                method,
                body: method === 'DELETE' ? undefined : body,
            });
            if (endpoint === '/api/projects') {
                const projectName = String(payload.project?.name || body.name || '');
                const message = status === 202 ? 'Project created. Ingestion queued.' : 'Project created.';
                window.location.assign(`/projects/${encodeURIComponent(projectName)}?message=${encodeURIComponent(message)}`);
                return;
            }

            if (endpoint.includes('/reingest')) {
                const projectName = form.getAttribute('data-async-project') || projectEndpointName(endpoint);
                const message = 'Reingest queued.';
                window.location.assign(`/projects/${encodeURIComponent(projectName)}?message=${encodeURIComponent(message)}`);
                return;
            }

            if (method === 'DELETE') {
                const projectName = form.getAttribute('data-async-project') || projectEndpointName(endpoint);
                window.location.assign(`/projects?message=${encodeURIComponent(`Project ${projectName} removed.`)}`);
                return;
            }

            flash('Operation completed.');
            window.location.reload();
        } catch (error) {
            flash(error.message, 'error');
        } finally {
            if (submitButton) {
                submitButton.removeAttribute('disabled');
            }
        }
    };

    document.addEventListener('submit', handleAsyncForm);

    const activePage = document.body.dataset.page || '';
    if (activePage === 'projects') {
        void loadProjectsPage();
    }
    if (activePage === 'projects' || document.querySelector('[data-project-name]')) {
        void loadProjectPage();
    }
    if (activePage === 'logs') {
        void loadLogsPage();
    }
})();
