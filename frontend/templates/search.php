<?php
/** @var string $mode */
/** @var string $project */
/** @var string $query */
/** @var string $filePath */
/** @var string $scopeType */
/** @var int $limit */
/** @var array<int,array<string,mixed>> $results */
/** @var string $error */
?>
<section class="card">
    <h2>Search</h2>
    <form method="get" action="/search">
        <div class="form-row">
            <div>
                <label>Mode</label>
                <select name="mode">
                    <?php foreach (['unified', 'lexical', 'semantic', 'tree-sitter', 'ast'] as $option) : ?>
                        <option value="<?= $escape($option) ?>" <?= $mode === $option ? 'selected' : '' ?>><?= $escape($option) ?></option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div>
                <label>Project</label>
                <input name="project" value="<?= $escape($project) ?>" placeholder="Optional project name">
            </div>
            <div>
                <label>Query</label>
                <input name="query" value="<?= $escape($query) ?>" placeholder="Search text">
            </div>
            <div>
                <label>Limit</label>
                <input name="limit" type="number" min="1" max="50" value="<?= $escape($limit) ?>">
            </div>
        </div>
        <div class="form-row" style="margin-top:12px;">
            <div>
                <label>File path</label>
                <input name="file_path" value="<?= $escape($filePath) ?>" placeholder="Required for tree-sitter / AST">
            </div>
            <div>
                <label>Scope type</label>
                <input name="scope_type" value="<?= $escape($scopeType) ?>" placeholder="Optional">
            </div>
            <div></div>
            <div></div>
        </div>
        <div class="actions">
            <button type="submit">Run search</button>
            <a class="button secondary" href="/search">Clear</a>
        </div>
    </form>
</section>

<?php if (!empty($error)) : ?>
    <div class="banner error" style="margin-top:18px;"><?= $escape($error) ?></div>
<?php endif; ?>

<section class="card" style="margin-top:18px;">
    <h3>Results</h3>
    <?php if ($results === []) : ?>
        <p class="muted">Run a query to see search output.</p>
    <?php else : ?>
        <div class="list">
            <?php foreach ($results as $result) : ?>
                <article class="list-item">
                    <div class="topbar" style="margin-bottom:0; align-items:flex-start;">
                        <div>
                            <strong><?= $escape($result['index_type'] ?? '') ?></strong>
                            <div class="muted"><?= $escape($result['project'] ?? '') ?> / <?= $escape($result['file_path'] ?? '') ?></div>
                            <?php if (!empty($result['symbol_name'])) : ?>
                                <div class="muted">Symbol: <?= $escape($result['symbol_name']) ?></div>
                            <?php endif; ?>
                        </div>
                        <?php if (array_key_exists('score', $result) && $result['score'] !== null) : ?>
                            <span class="pill">Score <?= $escape(number_format((float) $result['score'], 3)) ?></span>
                        <?php endif; ?>
                    </div>
                    <?php if (!empty($result['source_link']['href'])) : ?>
                        <div class="actions" style="margin-top:12px;">
                            <a class="button secondary" href="<?= $escape($result['source_link']['href']) ?>">View source</a>
                        </div>
                    <?php endif; ?>
                    <?php if (!empty($result['backends'])) : ?>
                        <div class="pills" style="margin-top:12px;">
                            <?php foreach ((array) $result['backends'] as $backend) : ?>
                                <span class="pill"><?= $escape($backend) ?></span>
                            <?php endforeach; ?>
                        </div>
                    <?php endif; ?>
                    <?php if (!empty($result['skeleton'])) : ?>
                        <div class="code" style="margin-top:12px;"><?= $escape($result['skeleton']) ?></div>
                    <?php elseif (!empty($result['symbols'])) : ?>
                        <div class="code" style="margin-top:12px;"><?= $escape(json_encode($result['symbols'], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE)) ?></div>
                    <?php endif; ?>
                </article>
            <?php endforeach; ?>
        </div>
    <?php endif; ?>
</section>
