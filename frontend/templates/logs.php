<?php
/** @var array<int,array<string,mixed>> $projects */
/** @var array<int,array<string,mixed>> $jobs */
/** @var string $selectedProject */
/** @var string $message */
/** @var string $error */
?>
<section class="card">
    <h2>Activity and ingestion jobs</h2>
    <form method="get" action="/logs">
        <div class="form-row">
            <div>
                <label>Project filter</label>
                <select name="project">
                    <option value="">All projects</option>
                    <?php foreach ($projects as $project) : ?>
                        <?php $name = (string) ($project['name'] ?? ''); ?>
                        <option value="<?= $escape($name) ?>" <?= $selectedProject === $name ? 'selected' : '' ?>><?= $escape($name) ?></option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div></div>
            <div></div>
            <div></div>
        </div>
        <div class="actions">
            <button type="submit">Filter</button>
            <a class="button secondary" href="/logs">Reset</a>
        </div>
    </form>
</section>

<?php if (!empty($message)) : ?>
    <div class="banner" style="margin-top:18px;"><?= $escape($message) ?></div>
<?php endif; ?>
<?php if (!empty($error)) : ?>
    <div class="banner error" style="margin-top:18px;"><?= $escape($error) ?></div>
<?php endif; ?>

<section class="card" style="margin-top:18px;">
    <h3>Jobs</h3>
    <?php if ($jobs === []) : ?>
        <p class="muted">No job records were returned.</p>
    <?php else : ?>
        <div class="list">
            <?php foreach ($jobs as $job) : ?>
                <article class="list-item">
                    <div class="topbar" style="margin-bottom:0; align-items:flex-start;">
                        <div>
                            <strong><?= $escape($job['project'] ?? '') ?></strong>
                            <div class="muted">Job <?= $escape($job['job_id'] ?? '') ?> · <?= $escape($job['action'] ?? '') ?> · <?= $escape($job['phase'] ?? '') ?></div>
                        </div>
                        <span class="pill"><?= $escape($job['status'] ?? '') ?></span>
                    </div>
                    <div class="kv" style="margin-top:12px;">
                        <div><strong>Queued:</strong> <?= $escape($job['queued_at'] ?? '—') ?></div>
                        <div><strong>Started:</strong> <?= $escape($job['started_at'] ?? '—') ?></div>
                        <div><strong>Updated:</strong> <?= $escape($job['updated_at'] ?? '—') ?></div>
                        <div><strong>Completed:</strong> <?= $escape($job['completed_at'] ?? '—') ?></div>
                    </div>
                    <div class="pills" style="margin-top:12px;">
                        <a class="pill" href="/projects/<?= rawurlencode((string) ($job['project'] ?? '')) ?>">Open project</a>
                        <a class="pill" href="/search?mode=unified&project=<?= rawurlencode((string) ($job['project'] ?? '')) ?>">Search project</a>
                    </div>
                    <?php if (!empty($job['last_error'])) : ?>
                        <p class="banner error" style="margin-top:12px;"><?= $escape($job['last_error']) ?></p>
                    <?php endif; ?>
                </article>
            <?php endforeach; ?>
        </div>
    <?php endif; ?>
</section>
