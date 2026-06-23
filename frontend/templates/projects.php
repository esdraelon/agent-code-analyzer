<?php
/** @var string $message */
/** @var string $error */
?>
<?php if (!empty($message)) : ?>
    <div class="banner"><?= $escape($message) ?></div>
<?php endif; ?>
<?php if (!empty($error)) : ?>
    <div class="banner error"><?= $escape($error) ?></div>
<?php endif; ?>

<div class="grid two">
    <section class="card">
        <h2>Onboard a project</h2>
        <form method="post" action="/projects/create" data-async-endpoint="/api/projects">
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
        <p class="muted" style="margin-bottom:0;">Project registration, reingest, and offboard actions run asynchronously in the browser.</p>
    </section>
</div>

<section class="card" style="margin-top:18px;">
    <div class="topbar" style="margin-bottom:12px;">
        <h2 style="margin:0;">Projects</h2>
        <span class="pill" id="projects-count">Loading…</span>
    </div>
    <div id="projects-status" class="muted">Loading projects asynchronously.</div>
    <div id="projects-list" class="list" style="margin-top:14px;"></div>
</section>
