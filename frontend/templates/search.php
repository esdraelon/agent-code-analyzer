<?php
/** @var string $mode */
/** @var string $project */
/** @var string $query */
/** @var string $filePath */
/** @var string $directory */
/** @var string $scopeType */
/** @var string $symbolPath */
/** @var int $pageSize */
/** @var int $page */
/** @var int $offset */
/** @var bool $hasPreviousPage */
/** @var bool $hasNextPage */
/** @var array<int,array<string,mixed>> $results */
/** @var array<int,array<string,mixed>> $projects */
/** @var string $error */
/** @var string $apiBaseUrl */
/** @var int $totalHits */
?>
<?php
$buildSearchHref = static function (int $targetPage) use ($mode, $project, $query, $filePath, $directory, $scopeType, $symbolPath, $pageSize): string {
    return '/search?' . http_build_query(array_filter([
        'mode' => $mode,
        'project' => $project !== '' ? $project : null,
        'query' => $query !== '' ? $query : null,
        'file_path' => $filePath !== '' ? $filePath : null,
        'directory' => $directory !== '' ? $directory : null,
        'scope_type' => $scopeType !== '' ? $scopeType : null,
        'symbol_path' => $symbolPath !== '' ? $symbolPath : null,
        'page_size' => $pageSize,
        'page' => $targetPage,
    ], static fn (mixed $value): bool => $value !== null && $value !== ''));
};

$pageStart = $results === [] ? 0 : $offset + 1;
$pageEnd = $offset + count($results);
?>
<section class="card hero">
    <div class="eyebrow">Search</div>
    <h2 style="margin-bottom:8px;">Structured retrieval across lexical, semantic, and source views</h2>
    <p class="muted" style="margin:0;">Use query + project filters for ranked retrieval, or file path for tree and AST drill-through.</p>
</section>

<section class="card" style="margin-top:18px;">
    <form method="get" action="/search" id="search-form">
        <div class="form-row">
            <div>
                <label>Mode</label>
                <select name="mode" id="search-mode">
                    <?php foreach (['unified', 'lexical', 'semantic', 'tree-sitter', 'ast'] as $option) : ?>
                        <option value="<?= $escape($option) ?>" <?= $mode === $option ? 'selected' : '' ?>><?= $escape($option) ?></option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div>
                <label>Project</label>
                <input name="project" id="search-project" list="project-options" value="<?= $escape($project) ?>" placeholder="Start typing a project name" autocomplete="off">
                <datalist id="project-options">
                    <?php foreach ($projects as $projectItem) : ?>
                        <?php $name = (string) ($projectItem['name'] ?? ''); ?>
                        <?php if ($name !== '') : ?>
                            <option value="<?= $escape($name) ?>"></option>
                        <?php endif; ?>
                    <?php endforeach; ?>
                </datalist>
            </div>
            <div>
                <label>Query</label>
                <input name="query" id="search-query" value="<?= $escape($query) ?>" placeholder="Search text">
            </div>
            <div>
                <label>Page size</label>
                <input name="page_size" type="number" min="1" max="50" value="<?= $escape($pageSize) ?>">
            </div>
        </div>
        <div class="form-row" style="margin-top:12px;">
            <div>
                <label>Directory</label>
                <input name="directory" id="search-directory" list="directory-options" value="<?= $escape($directory) ?>" placeholder="Restrict results to this directory" autocomplete="off">
                <datalist id="directory-options"></datalist>
            </div>
            <div>
                <label>File path</label>
                <input name="file_path" id="search-file-path" list="file-path-options" value="<?= $escape($filePath) ?>" placeholder="Required for tree-sitter / AST" autocomplete="off">
                <datalist id="file-path-options"></datalist>
            </div>
            <div>
                <label>Scope type</label>
                <select name="scope_type" id="search-scope-type">
                    <option value="" <?= $scopeType === '' ? 'selected' : '' ?>>Any</option>
                    <?php foreach (['file', 'symbol', 'chunk'] as $option) : ?>
                        <option value="<?= $escape($option) ?>" <?= $scopeType === $option ? 'selected' : '' ?>><?= $escape($option) ?></option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div>
                <label>Tree-sitter path</label>
                <input name="symbol_path" id="search-symbol-path" value="<?= $escape($symbolPath) ?>" placeholder="Restrict results to this scope path" autocomplete="off">
            </div>
        </div>
        <div class="actions">
            <button type="submit">Run search</button>
            <a class="button secondary" href="/search">Clear</a>
        </div>
    </form>
</section>

<script>
(() => {
    const projectInput = document.getElementById('search-project');
    const directoryInput = document.getElementById('search-directory');
    const filePathInput = document.getElementById('search-file-path');
    const directoryList = document.getElementById('directory-options');
    const filePathList = document.getElementById('file-path-options');
    if (!projectInput || !directoryInput || !filePathInput || !directoryList || !filePathList) {
        return;
    }

    const endpoint = '/api/projects/';
    let timer = null;

    const clearOptions = (list) => {
        list.replaceChildren();
    };

    const renderOptions = (list, values) => {
        list.replaceChildren(...values.map((value) => {
            const option = document.createElement('option');
            option.value = value;
            return option;
        }));
    };

    const fetchPaths = async (kind, prefix, list) => {
        const project = projectInput.value.trim();
        if (!project) {
            clearOptions(list);
            return;
        }
        const url = new URL(endpoint + encodeURIComponent(project) + '/paths', window.location.origin);
        url.searchParams.set('kind', kind);
        url.searchParams.set('prefix', prefix);
        url.searchParams.set('limit', '25');
        try {
            const response = await fetch(url.toString(), { headers: { 'Accept': 'application/json' } });
            if (!response.ok) {
                clearOptions(list);
                return;
            }
            const payload = await response.json();
            const values = Array.isArray(payload.paths) ? payload.paths : [];
            renderOptions(list, values.slice(0, 25));
        } catch (error) {
            clearOptions(list);
        }
    };

    const refresh = () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => {
            const directoryPrefix = directoryInput.value.trim();
            const filePathPrefix = filePathInput.value.trim();

            if (directoryPrefix.length >= 2) {
                void fetchPaths('directory', directoryPrefix, directoryList);
            } else {
                clearOptions(directoryList);
            }

            if (filePathPrefix.length >= 2) {
                void fetchPaths('file', filePathPrefix, filePathList);
            } else {
                clearOptions(filePathList);
            }
        }, 180);
    };

    projectInput.addEventListener('input', refresh);
    directoryInput.addEventListener('input', refresh);
    filePathInput.addEventListener('input', refresh);
    projectInput.addEventListener('change', refresh);
})();
</script>

<?php if (!empty($error)) : ?>
    <div class="banner error" style="margin-top:18px;"><?= $escape($error) ?></div>
<?php endif; ?>

<section class="card" style="margin-top:18px;">
    <div class="topbar" style="margin-bottom:12px;">
        <h3 style="margin:0;">Results</h3>
        <div class="actions" style="gap:8px; flex-wrap:wrap; justify-content:flex-end;">
            <span class="pill">Page <?= $escape((string) $page) ?></span>
            <?php if ($results !== []) : ?>
                <span class="pill"><?= $escape(sprintf('%d-%d', $pageStart, $pageEnd)) ?> of <?= $escape((string) $totalHits) ?></span>
            <?php endif; ?>
            <span class="pill"><?= $escape(count($results)) ?> hits of <?= $escape((string) $totalHits) ?></span>
            <?php if ($hasPreviousPage) : ?>
                <a class="button secondary" href="<?= $escape($buildSearchHref($page - 1)) ?>">Prev</a>
            <?php endif; ?>
            <?php if ($hasNextPage) : ?>
                <a class="button secondary" href="<?= $escape($buildSearchHref($page + 1)) ?>">Next</a>
            <?php endif; ?>
        </div>
    </div>
    <?php if ($results === []) : ?>
        <p class="muted">Run a query to see search output.</p>
    <?php else : ?>
        <div class="list">
            <?php foreach ($results as $result) : ?>
                <?php
                $sourceLink = $result['source_link'] ?? [];
                $sourceProject = (string) ($sourceLink['project'] ?? $result['project'] ?? '');
                $sourceFile = (string) ($sourceLink['file_path'] ?? $result['file_path'] ?? '');
                $sourceStart = $sourceLink['start_line'] ?? null;
                $sourceEnd = $sourceLink['end_line'] ?? null;
                $sourceSymbol = (string) ($sourceLink['symbol_name'] ?? $result['symbol_name'] ?? '');
                $viewerHref = '';
                if ($sourceProject !== '' && $sourceFile !== '') {
                    $viewerHref = '/source?' . http_build_query(array_filter([
                        'project' => $sourceProject,
                        'file_path' => $sourceFile,
                        'start_line' => $sourceStart,
                        'end_line' => $sourceEnd,
                        'symbol_name' => $sourceSymbol !== '' ? $sourceSymbol : null,
                    ], static fn (mixed $value): bool => $value !== null && $value !== ''));
                }
                $rangeLabel = '—';
                if (is_int($sourceStart) || is_int($sourceEnd)) {
                    $rangeLabel = trim(sprintf('%s%s', $sourceStart !== null ? (string) $sourceStart : '?', $sourceEnd !== null ? '–' . $sourceEnd : ''));
                }
                ?>
                <article class="list-item result-card">
                    <div class="topbar" style="margin-bottom:0; align-items:flex-start;">
                        <div>
                            <div class="result-title-row">
                                <strong><?= $escape($result['index_type'] ?? '') ?></strong>
                                <?php if (array_key_exists('score', $result) && $result['score'] !== null) : ?>
                                    <span class="pill">Score <?= $escape(number_format((float) $result['score'], 3)) ?></span>
                                <?php endif; ?>
                            </div>
                            <div class="muted mono"><?= $escape(($result['project'] ?? '') . ' / ' . ($result['file_path'] ?? '')) ?></div>
                            <div class="detail-grid compact" style="margin-top:10px;">
                                <div><span class="detail-label">Symbol</span><div><?= $escape((string) ($result['symbol_name'] ?? '—')) ?></div></div>
                                <div><span class="detail-label">Lines</span><div><?= $escape($rangeLabel) ?></div></div>
                                <div><span class="detail-label">Scope</span><div><?= $escape((string) ($result['scope_type'] ?? '—')) ?></div></div>
                                <div><span class="detail-label">Unit</span><div><?= $escape((string) ($result['unit_type'] ?? $result['source_kind'] ?? '—')) ?></div></div>
                                <div><span class="detail-label">Root type</span><div><?= $escape((string) ($result['root_type'] ?? '—')) ?></div></div>
                                <div><span class="detail-label">Language</span><div><?= $escape((string) ($result['languages'][0] ?? $result['language'] ?? '—')) ?></div></div>
                            </div>
                            <?php if (!empty($result['source_link'])) : ?>
                                <div class="muted" style="margin-top:10px;">
                                    Source: <?= $escape($sourceProject) ?> / <?= $escape($sourceFile) ?>
                                    <?php if ($sourceSymbol !== '') : ?>· <?= $escape($sourceSymbol) ?><?php endif; ?>
                                </div>
                            <?php endif; ?>
                        </div>
                    </div>

                    <?php if ($viewerHref !== '') : ?>
                        <div class="actions" style="margin-top:12px;">
                            <a class="button secondary" href="<?= $escape($viewerHref) ?>">View source</a>
                            <a class="button secondary" href="/search?mode=unified&project=<?= rawurlencode($sourceProject) ?>&query=<?= rawurlencode($sourceSymbol !== '' ? $sourceSymbol : $sourceFile) ?>">Search nearby</a>
                        </div>
                    <?php endif; ?>

                    <?php if (!empty($result['backends'])) : ?>
                        <div class="pills" style="margin-top:12px;">
                            <?php foreach ((array) $result['backends'] as $backend) : ?>
                                <span class="pill"><?= $escape($backend) ?></span>
                            <?php endforeach; ?>
                        </div>
                    <?php endif; ?>

                    <?php if (!empty($result['related_index_links'])) : ?>
                        <div class="pills related-links" style="margin-top:12px;">
                            <?php foreach ((array) $result['related_index_links'] as $link) : ?>
                                <?php
                                $rel = (string) ($link['rel'] ?? 'link');
                                $relatedHref = $link['href'] ?? '#';
                                if ($rel === 'source') {
                                    $relatedHref = $viewerHref !== '' ? $viewerHref : $relatedHref;
                                } elseif (in_array($rel, ['tree-sitter', 'ast'], true)) {
                                    $relatedHref = '/search?' . http_build_query(array_filter([
                                        'mode' => $rel,
                                        'project' => $sourceProject,
                                        'file_path' => $sourceFile,
                                    ], static fn (mixed $value): bool => $value !== null && $value !== ''));
                                } elseif (in_array($rel, ['lexical', 'semantic', 'unified'], true)) {
                                    $relatedHref = '/search?' . http_build_query(array_filter([
                                        'mode' => $rel === 'unified' ? 'unified' : $rel,
                                        'project' => $sourceProject,
                                        'query' => $sourceSymbol !== '' ? $sourceSymbol : $sourceFile,
                                    ], static fn (mixed $value): bool => $value !== null && $value !== ''));
                                }
                                ?>
                                <a class="pill" href="<?= $escape((string) $relatedHref) ?>"><?= $escape($rel) ?></a>
                            <?php endforeach; ?>
                        </div>
                    <?php endif; ?>

                    <?php if (!empty($result['excerptRows'])) : ?>
                        <div class="source-excerpt" style="margin-top:12px;">
                            <?php foreach ((array) $result['excerptRows'] as $row) : ?>
                                <div class="source-line">
                                    <span class="source-line-no"><?= $escape((string) ($row['line_no'] ?? '·')) ?></span>
                                    <span class="source-line-text syntax"><?= $row['html'] ?? '' ?></span>
                                </div>
                            <?php endforeach; ?>
                        </div>
                    <?php endif; ?>

                    <?php if (!empty($result['skeleton'])) : ?>
                        <div class="code tiny" style="margin-top:12px;"><?= $escape((string) $result['skeleton']) ?></div>
                    <?php elseif (!empty($result['symbols'])) : ?>
                        <div class="code tiny" style="margin-top:12px;"><?= $escape(json_encode($result['symbols'], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE)) ?></div>
                    <?php endif; ?>
                </article>
            <?php endforeach; ?>
        </div>
    <?php endif; ?>
</section>
