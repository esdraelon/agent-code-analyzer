FROM composer:2 AS vendor
WORKDIR /app
COPY composer.json ./
RUN composer install --no-interaction --no-progress --prefer-dist --ignore-platform-req=php

FROM php:8.4-cli-bookworm
WORKDIR /app
COPY --from=vendor /app/vendor ./vendor
COPY . .
EXPOSE 40080
CMD ["sh", "-lc", "php -S 0.0.0.0:${APP_PORT:-40080} -t public public/index.php"]
