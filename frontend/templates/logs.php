<?php
/** @var string $selectedProject */
/** @var string $message */
/** @var string $error */
?>
<section class="card">
    <h2>Activity and ingestion jobs</h2>
    <form method="get" action="/logs" id="logs-filter-form">
        <div class="form-row">
            <div>
                <label>Project filter</label>
                <select name="project" id="logs-project-select">
                    <option value="">Loading projects…</option>
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
    <div class="topbar" style="margin-bottom:12px;">
        <h3 style="margin:0;">Jobs</h3>
        <span class="pill" id="logs-job-count">Loading…</span>
    </div>
    <div id="logs-jobs" class="muted">Loading jobs asynchronously.</div>
</section>
