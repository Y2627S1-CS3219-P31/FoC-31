#!/bin/sh
set -e
# Inject the runtime API base URL so the image needs no rebuild when it changes.
export API_BASE_URL="${API_BASE_URL:-}"
envsubst '${API_BASE_URL}' < /config.js.template > /usr/share/nginx/html/config.js
exec nginx -g 'daemon off;'
