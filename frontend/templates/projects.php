<?php
/** @var array<int,array<string,mixed>> $projects */
/** @var string $message */
?>
<?php if (!empty($message)) : ?>
    <div class="banner"><?= $escape($message) ?></div>
<?php endif; ?>

<div class="grid two">
    <section class="card">
        <h2>Onboard a project</h2>
        <form method="post" action="/projects/create">
            <div class="grid" style="gap:12px;">
                <input name="name" placeholder="Project name" required>
                <input name="root_path" placeholder="Root path, for example /home/hal9k/host-tools/agent-code-analyzer" required>
                <select name="mode">
                    <option value="directory">directory</option>
                    <option value="file">file</option>
                </select>
                <textarea name="description" placeholder="Optional description"></textarea>
            </div>
            <div class="actions">
                <button type="submit">Create project</button>
            </div>
        </form>
    </section>

    <section class="card">
        <h2>How it works</h2>
        <p class="muted">This frontend talks only to the HTTP control API. The Python MCP server stays intact for agent use.</p>
        <div class="pills">
            <span class="pill">List projects</span>
            <span class="pill">Reingest</span>
            <span class="pill">Search</span>
            <span class="pill">Jobs</span>
            <span class="pill">Source drill-through</span>
        </div>
    </section>
</div>

<section class="card" style="margin-top:18px;">
    <h2>Projects</h2>
    <?php if ($projects === []) : ?>
        <p class="muted">No projects are registered yet.</p>
    <?php else : ?>
        <div class="list">
            <?php foreach ($projects as $project) : ?>
                <article class="list-item">
                    <div class="topbar" style="margin-bottom:0; align-items:flex-start;">
                        <div>
                            <h3 style="margin-bottom:6px;"><a href="/projects/<?= rawurlencode((string) ($project['name'] ?? '')) ?>"><?= $escape($project['name'] ?? '') ?></a></h3>
                            <div class="muted"><?= $escape($project['root_path'] ?? '') ?></div>
                        </div>
                        <span class="pill"><?= $escape($project['status'] ?? 'idle') ?></span>
                    </div>
                    <div class="kv" style="margin-top:14px;">
                        <div><strong>Mode:</strong> <?= $escape($project['mode'] ?? '') ?></div>
                        <div><strong>Indexed:</strong> <?= $escape($project['indexed_at'] ?? '—') ?></div>
                        <div><strong>Files:</strong> <?= $escape($project['file_count'] ?? 0) ?></div>
                        <div><strong>Symbols:</strong> <?= $escape($project['symbol_count'] ?? 0) ?></div>
                    </div>
                    <?php if (!empty($project['description'])) : ?>
                        <p class="muted" style="margin-bottom:0;"><?= $escape($project['description']) ?></p>
                    <?php endif; ?>
                    <div class="actions">
                        <a class="button secondary" href="/projects/<?= rawurlencode((string) ($project['name'] ?? '')) ?>">Open</a>
                        <form method="post" action="/projects/<?= rawurlencode((string) ($project['name'] ?? '')) ?>/reingest">
                            <input type="hidden" name="mode" value="refresh">
                            <input type="hidden" name="refresh" value="true">
                            <button type="submit">Reingest</button>
                        </form>
                        <form method="post" action="/projects/<?= rawurlencode((string) ($project['name'] ?? '')) ?>/offboard" onsubmit="return confirm('Remove this project and its indexes?');">
                            <button type="submit" class="danger">Offboard</button>
                        </form>
                    </div>
                </article>
            <?php endforeach; ?>
        </div>
    <?php endif; ?>
</section>
