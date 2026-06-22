<?php
/** @var string $pageTitle */
/** @var string $content */
/** @var string $appName */
/** @var string $activePage */
?>
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title><?= $escape($pageTitle) ?></title>
    <link rel="stylesheet" href="/assets/app.css">
</head>
<body>
<div class="shell">
    <header class="topbar">
        <div class="brand">
            <h1><?= $escape($appName) ?></h1>
            <p>Control-plane dashboard for the analyzer and operator flows.</p>
        </div>
        <nav class="nav">
            <a class="<?= ($activePage ?? '') === 'projects' ? 'active' : '' ?>" href="/projects">Projects</a>
            <a class="<?= ($activePage ?? '') === 'search' ? 'active' : '' ?>" href="/search">Search</a>
            <a class="<?= ($activePage ?? '') === 'logs' ? 'active' : '' ?>" href="/logs">Jobs</a>
        </nav>
    </header>

    <?= $content ?>
</div>
</body>
</html>
