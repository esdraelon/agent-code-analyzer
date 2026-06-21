<?php
/** @var array<string,mixed> $project */
/** @var array<int,array<string,mixed>> $jobs */
/** @var string $message */
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
