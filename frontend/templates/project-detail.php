<?php
/** @var array<string,mixed> $project */
/** @var array<int,array<string,mixed>> $jobs */
/** @var string $message */
?>
<?php
$indexSummary = is_array($project['index_summary'] ?? null) ? $project['index_summary'] : [];
$hardSummary = is_array($indexSummary['hard'] ?? null) ? $indexSummary['hard'] : [];
$softSummary = is_array($indexSummary['soft'] ?? null) ? $indexSummary['soft'] : [];
$renderBreakdown = static function (array $items) use ($escape): void {
    if ($items === []) {
        echo '<p class="muted" style="margin:10px 0 0;">No entries yet.</p>';
        return;
    }

    echo '<ul class="breakdown-list">';
    foreach ($items as $item) {
        $label = $escape((string) ($item['label'] ?? $item['key'] ?? ''));
        $count = $escape((string) ($item['count'] ?? 0));
        echo '<li><span class="label">' . $label . '</span><span class="count">' . $count . '</span></li>';
    }
    echo '</ul>';
};
?>
<?php if (!empty($message)) : ?>
    <div class="banner"><?= $escape($message) ?></div>
<?php endif; ?>

<section class="card">
    <div class="topbar" style="margin-bottom:0; align-items:flex-start;">
        <div>
            <h2 style="margin-bottom:6px;"><?= $escape($project['name'] ?? '') ?></h2>
            <div class="muted"><?= $escape($project['root_path'] ?? '') ?></div>
        </div>
        <span class="pill"><?= $escape($project['status'] ?? 'idle') ?></span>
    </div>

    <div class="kv" style="margin-top:16px;">
        <div><strong>Mode:</strong> <?= $escape($project['mode'] ?? '') ?></div>
        <div><strong>Created:</strong> <?= $escape($project['created_at'] ?? '—') ?></div>
        <div><strong>Updated:</strong> <?= $escape($project['updated_at'] ?? '—') ?></div>
        <div><strong>Indexed:</strong> <?= $escape($project['indexed_at'] ?? '—') ?></div>
        <div><strong>Files:</strong> <?= $escape($project['file_count'] ?? 0) ?></div>
        <div><strong>Symbols:</strong> <?= $escape($project['symbol_count'] ?? 0) ?></div>
    </div>

    <?php if (!empty($project['description'])) : ?>
        <p><?= $escape($project['description']) ?></p>
    <?php endif; ?>

    <div class="actions">
        <form method="post" action="/projects/<?= rawurlencode((string) ($project['name'] ?? '')) ?>/reingest">
            <input type="hidden" name="mode" value="refresh">
            <input type="hidden" name="refresh" value="true">
            <button type="submit">Reingest now</button>
        </form>
        <form method="post" action="/projects/<?= rawurlencode((string) ($project['name'] ?? '')) ?>/offboard" onsubmit="return confirm('Remove this project and its indexes?');">
            <button type="submit" class="danger">Offboard project</button>
        </form>
        <a class="button secondary" href="/search?project=<?= rawurlencode((string) ($project['name'] ?? '')) ?>">Search this project</a>
    </div>
</section>

<section class="card" style="margin-top:18px;">
    <div class="eyebrow">Index overview</div>
    <div class="detail-grid quad">
        <div>
            <span class="detail-label">Hard entries</span>
            <strong><?= $escape((int) ($indexSummary['hard_total'] ?? $project['file_count'] ?? 0)) ?></strong>
            <div class="muted">Lexical / AST-backed entries</div>
        </div>
        <div>
            <span class="detail-label">Soft entries</span>
            <strong><?= $escape((int) ($indexSummary['soft_total'] ?? 0)) ?></strong>
            <div class="muted">Semantic / model-backed entries</div>
        </div>
        <div>
            <span class="detail-label">Lexical docs</span>
            <strong><?= $escape((int) ($indexSummary['lexical_total'] ?? 0)) ?></strong>
            <div class="muted">Hard tree-sitter documents</div>
        </div>
        <div>
            <span class="detail-label">Semantic points</span>
            <strong><?= $escape((int) ($indexSummary['semantic_total'] ?? 0)) ?></strong>
            <div class="muted">Soft Qdrant entries</div>
        </div>
    </div>

    <details class="details-toggle">
        <summary>Hard breakdown — AST and lexical counts</summary>
        <div class="detail-grid" style="margin-top:12px;">
            <div>
                <span class="detail-label">Tree-sitter symbol types</span>
                <?php $renderBreakdown(is_array($hardSummary['symbol_type_counts'] ?? null) ? $hardSummary['symbol_type_counts'] : []); ?>
            </div>
            <div>
                <span class="detail-label">Lexical document scopes</span>
                <?php $renderBreakdown(is_array($hardSummary['lexical_scope_counts'] ?? null) ? $hardSummary['lexical_scope_counts'] : []); ?>
            </div>
            <div>
                <span class="detail-label">Lexical symbol unit types</span>
                <?php $renderBreakdown(is_array($hardSummary['lexical_symbol_unit_counts'] ?? null) ? $hardSummary['lexical_symbol_unit_counts'] : []); ?>
            </div>
        </div>
    </details>

    <details class="details-toggle">
        <summary>Soft breakdown — semantic counts</summary>
        <div class="detail-grid" style="margin-top:12px;">
            <div>
                <span class="detail-label">Semantic source kinds</span>
                <?php $renderBreakdown(is_array($softSummary['source_kind_counts'] ?? null) ? $softSummary['source_kind_counts'] : []); ?>
            </div>
            <div>
                <span class="detail-label">Semantic unit types</span>
                <?php $renderBreakdown(is_array($softSummary['unit_type_counts'] ?? null) ? $softSummary['unit_type_counts'] : []); ?>
            </div>
        </div>
    </details>
</section>

<section class="grid two" style="margin-top:18px;">
    <div class="card">
        <h3>Ingestion job</h3>
        <?php if ($jobs === []) : ?>
            <p class="muted">No job records are available yet.</p>
        <?php else : ?>
            <?php $job = $jobs[0]; ?>
            <div class="kv">
                <div><strong>Job ID:</strong> <?= $escape($job['job_id'] ?? '') ?></div>
                <div><strong>Status:</strong> <?= $escape($job['status'] ?? '') ?></div>
                <div><strong>Action:</strong> <?= $escape($job['action'] ?? '') ?></div>
                <div><strong>Phase:</strong> <?= $escape($job['phase'] ?? '') ?></div>
                <div><strong>Queued:</strong> <?= $escape($job['queued_at'] ?? '—') ?></div>
                <div><strong>Completed:</strong> <?= $escape($job['completed_at'] ?? '—') ?></div>
            </div>
            <?php if (!empty($job['last_error'])) : ?>
                <p class="banner error"><?= $escape($job['last_error']) ?></p>
            <?php endif; ?>
        <?php endif; ?>
    </div>

    <div class="card">
        <h3>Quick links</h3>
        <div class="pills">
            <a class="pill" href="/projects">Back to list</a>
            <a class="pill" href="/search?mode=unified&project=<?= rawurlencode((string) ($project['name'] ?? '')) ?>">Unified search</a>
            <a class="pill" href="/logs?project=<?= rawurlencode((string) ($project['name'] ?? '')) ?>">Activity</a>
        </div>
    </div>
</section>
