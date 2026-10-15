#!/bin/bash
# Publish site/ to the Netlify project as a production deploy.
# Auth: NETLIFY_AUTH_TOKEN from .env, or the login saved by `npx netlify login`.
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && { set -a; source .env; set +a; }
[ -n "${NETLIFY_AUTH_TOKEN:-}" ] || unset NETLIFY_AUTH_TOKEN  # empty value would override the CLI login

: "${NETLIFY_SITE_ID:?Set NETLIFY_SITE_ID in .env}"
[ -f site/index.html ] || { echo "site/index.html missing - run build_site.py first" >&2; exit 1; }

./node_modules/.bin/netlify deploy \
  --prod \
  --dir site \
  --site "$NETLIFY_SITE_ID" \
  --message "Daily edition $(date +%Y-%m-%d)" \
  --no-build
