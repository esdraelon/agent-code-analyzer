<?php
/** @var string $projectName */
/** @var string $message */
/** @var string $error */
?>
<?php if (!empty($message)) : ?>
    <div class="banner"><?= $escape($message) ?></div>
<?php endif; ?>
<?php if (!empty($error)) : ?>
    <div class="banner error"><?= $escape($error) ?></div>
<?php endif; ?>

<section class="card" data-project-name="<?= $escape($projectName) ?>">
    <div class="topbar" style="margin-bottom:0; align-items:flex-start;">
        <div>
            <h2 style="margin-bottom:6px;" id="project-title"><?= $escape($projectName) ?></h2>
            <div class="muted" id="project-root-path">Loading project details…</div>
        </div>
        <span class="pill" id="project-status">Loading…</span>
    </div>

    <div class="kv" style="margin-top:16px;" id="project-kv">
        <div><strong>Mode:</strong> <span id="project-mode">—</span></div>
        <div><strong>Created:</strong> <span id="project-created">—</span></div>
        <div><strong>Updated:</strong> <span id="project-updated">—</span></div>
        <div><strong>Indexed:</strong> <span id="project-indexed">—</span></div>
        <div><strong>Files:</strong> <span id="project-files">—</span></div>
        <div><strong>Symbols:</strong> <span id="project-symbols">—</span></div>
    </div>

    <p id="project-description" class="muted" style="margin-top:14px; margin-bottom:0;">Project metadata will load asynchronously.</p>

    <div class="actions">
        <form method="post" action="/projects/<?= rawurlencode($projectName) ?>/reingest" data-async-endpoint="/api/projects/<?= rawurlencode($projectName) ?>/reingest">
            <input type="hidden" name="mode" value="refresh">
            <input type="hidden" name="refresh" value="true">
            <button type="submit">Reingest now</button>
        </form>
        <form method="post" action="/projects/<?= rawurlencode($projectName) ?>/offboard" data-async-endpoint="/api/projects/<?= rawurlencode($projectName) ?>" data-async-method="DELETE" onsubmit="return confirm('Remove this project and its indexes?');">
            <button type="submit" class="danger">Offboard project</button>
        </form>
        <a class="button secondary" href="/search?project=<?= rawurlencode($projectName) ?>">Search this project</a>
    </div>
</section>

<section class="card" style="margin-top:18px;">
    <div class="eyebrow">Index overview</div>
    <div class="detail-grid quad" id="project-index-overview">
        <div>
            <span class="detail-label">Hard entries</span>
            <strong>—</strong>
            <div class="muted">Lexical / AST-backed entries</div>
        </div>
        <div>
            <span class="detail-label">Soft entries</span>
            <strong>—</strong>
            <div class="muted">Semantic / model-backed entries</div>
        </div>
        <div>
            <span class="detail-label">Lexical docs</span>
            <strong>—</strong>
            <div class="muted">Hard tree-sitter documents</div>
        </div>
        <div>
            <span class="detail-label">Semantic points</span>
            <strong>—</strong>
            <div class="muted">Soft Qdrant entries</div>
        </div>
    </div>

    <details class="details-toggle">
        <summary>Hard breakdown — AST and lexical counts</summary>
        <div class="detail-grid" style="margin-top:12px;" id="project-hard-breakdown">
            <div>
                <span class="detail-label">Tree-sitter symbol types</span>
                <p class="muted" style="margin-top:10px;">Loading…</p>
            </div>
            <div>
                <span class="detail-label">Lexical document scopes</span>
                <p class="muted" style="margin-top:10px;">Loading…</p>
            </div>
            <div>
                <span class="detail-label">Lexical symbol unit types</span>
                <p class="muted" style="margin-top:10px;">Loading…</p>
            </div>
        </div>
    </details>

    <details class="details-toggle">
        <summary>Soft breakdown — semantic counts</summary>
        <div class="detail-grid" style="margin-top:12px;" id="project-soft-breakdown">
            <div>
                <span class="detail-label">Semantic source kinds</span>
                <p class="muted" style="margin-top:10px;">Loading…</p>
            </div>
            <div>
                <span class="detail-label">Semantic unit types</span>
                <p class="muted" style="margin-top:10px;">Loading…</p>
            </div>
        </div>
    </details>
</section>

<section class="grid two" style="margin-top:18px;">
    <div class="card">
        <h3>Ingestion job</h3>
        <div id="project-jobs" class="muted">Loading job records asynchronously.</div>
    </div>

    <div class="card">
        <h3>Quick links</h3>
        <div class="pills">
            <a class="pill" href="/projects">Back to list</a>
            <a class="pill" href="/search?mode=unified&project=<?= rawurlencode($projectName) ?>">Unified search</a>
            <a class="pill" href="/logs?project=<?= rawurlencode($projectName) ?>">Activity</a>
        </div>
    </div>
</section>
