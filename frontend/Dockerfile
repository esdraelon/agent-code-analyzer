FROM composer:2 AS vendor
WORKDIR /app
COPY composer.json ./
RUN composer install --no-interaction --no-progress --prefer-dist --ignore-platform-req=php

FROM php:8.4-cli-bookworm
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends $PHPIZE_DEPS \
    && pecl install apcu \
    && docker-php-ext-enable apcu \
    && printf "apc.enable_cli=1\napc.enabled=1\n" > /usr/local/etc/php/conf.d/99-apcu.ini \
    && rm -rf /var/lib/apt/lists/* /tmp/pear
COPY --from=vendor /app/vendor ./vendor
COPY . .
EXPOSE 40080
CMD ["sh", "-lc", "php -S 0.0.0.0:${APP_PORT:-40080} -t public public/index.php"]
