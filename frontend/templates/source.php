<?php
/** @var string $project */
/** @var string $filePath */
/** @var string $symbolName */
/** @var int $startLine */
/** @var int $endLine */
/** @var array<string,mixed> $summary */
/** @var array<string,mixed> $excerpt */
/** @var string $error */
/** @var string $astImageDataUrl */
?>
<section class="card hero">
    <div class="eyebrow">Source drill-through</div>
    <div class="topbar" style="margin-bottom:0; align-items:flex-start;">
        <div>
            <h2 style="margin-bottom:6px;"><?= $escape($filePath) ?></h2>
            <div class="muted">
                Project: <?= $escape($project) ?>
                <?php if (!empty($symbolName)) : ?>
                    · Symbol: <?= $escape($symbolName) ?>
                <?php endif; ?>
            </div>
        </div>
        <div class="pills">
            <?php if (!empty($summary['language'])) : ?><span class="pill"><?= $escape($summary['language']) ?></span><?php endif; ?>
            <?php if (!empty($summary['source_kind'])) : ?><span class="pill"><?= $escape($summary['source_kind']) ?></span><?php endif; ?>
            <?php if (!empty($summary['supported'])) : ?><span class="pill">Supported</span><?php endif; ?>
        </div>
    </div>
</section>

<?php if (!empty($error)) : ?>
    <div class="banner error" style="margin-top:18px;"><?= $escape($error) ?></div>
<?php endif; ?>

<section class="source-layout" style="margin-top:18px;">
    <div class="card source-panel source-panel-fixed">
        <h3>File details</h3>
        <div class="detail-grid">
            <div><span class="detail-label">Project</span><div><?= $escape($project) ?></div></div>
            <div><span class="detail-label">Path</span><div class="mono"><?= $escape($filePath) ?></div></div>
            <div><span class="detail-label">Excerpt</span><div><?= $escape($startLine) ?>–<?= $escape($endLine) ?></div></div>
            <div><span class="detail-label">Symbol</span><div><?= $escape($symbolName !== '' ? $symbolName : '—') ?></div></div>
            <div><span class="detail-label">Language</span><div><?= $escape($summary['language'] ?? '—') ?></div></div>
            <div><span class="detail-label">Supported</span><div><?= !empty($summary['supported']) ? 'yes' : 'no' ?></div></div>
        </div>

        <?php if (!empty($summary['symbol_health'])) : ?>
            <h4 style="margin-top:18px;">Symbol health</h4>
            <div class="code tiny source-mono"><?= $escape(json_encode($summary['symbol_health'], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE)) ?></div>
        <?php endif; ?>

        <div class="actions" style="margin-top:18px;">
            <a class="button secondary" href="/search?mode=unified&project=<?= rawurlencode($project) ?>&query=<?= rawurlencode($symbolName !== '' ? $symbolName : $filePath) ?>">Search nearby</a>
            <a class="button secondary" href="/projects/<?= rawurlencode($project) ?>">Project page</a>
        </div>
    </div>

    <div class="card ast-card source-panel-ast">
        <div class="topbar" style="margin-bottom:10px; align-items:flex-start;">
            <div>
                <h3 style="margin-bottom:6px;">Tree-sitter AST</h3>
                <div class="muted">Rendered from the parsed tree for this file.</div>
            </div>
            <?php if (!empty($summary['root_type'])) : ?>
                <span class="pill"><?= $escape((string) $summary['root_type']) ?></span>
            <?php endif; ?>
        </div>

        <?php if (!empty($astImageDataUrl)) : ?>
            <img class="ast-image" src="<?= $escape($astImageDataUrl) ?>" alt="Tree-sitter AST render for <?= $escape($filePath) ?>" loading="lazy">
        <?php else : ?>
            <div class="banner">No AST image available for this file.</div>
        <?php endif; ?>

        <div class="detail-grid compact" style="margin-top:14px;">
            <div><span class="detail-label">Nodes</span><div><?= $escape((string) ($summary['node_count'] ?? '—')) ?></div></div>
            <div><span class="detail-label">Symbols</span><div><?= $escape((string) count((array) ($summary['symbols'] ?? []))) ?></div></div>
            <div><span class="detail-label">Health</span><div><?= !empty($summary['symbol_health']['healthy']) ? 'healthy' : 'attention' ?></div></div>
        </div>
    </div>
</section>

<div class="card source-section-fixed" style="margin-top:18px;">
    <h3>Excerpt</h3>
    <div class="source-excerpt">
        <?php if (!empty($excerpt['content'])) : ?>
            <?php foreach ($excerptRows as $row) : ?>
                <div class="source-line">
                    <span class="source-line-no"><?= $escape((string) $row['line_no']) ?></span>
                    <span class="source-line-text syntax"><?= $row['html'] ?></span>
                </div>
            <?php endforeach; ?>
        <?php else : ?>
            <p class="muted">No excerpt returned.</p>
        <?php endif; ?>
    </div>
</div>

<?php if (!empty($summary['skeleton'])) : ?>
    <section class="card source-section-fixed" style="margin-top:18px;">
        <h3>Structure</h3>
        <div class="code source-mono"><?= $escape((string) $summary['skeleton']) ?></div>
    </section>
<?php endif; ?>

<?php if (!empty($summary['symbols'])) : ?>
    <section class="card source-section-fixed" style="margin-top:18px;">
        <h3>Symbols</h3>
        <div class="code tiny source-mono"><?= $escape(json_encode($summary['symbols'], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE)) ?></div>
    </section>
<?php endif; ?>
