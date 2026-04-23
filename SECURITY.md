# Security Policy

Do not publish real credentials, private game builds, generated `www/` output,
Cloudflare API tokens, access-code databases, or Worker signing secrets in this
repository.

If you deploy with `--enable-kv-auth`, configure `ACCESS_SECRET_KEY` in
Cloudflare Pages environment variables. Do not hardcode it in `_worker.js`.

Report security issues privately to the project maintainer instead of opening a
public issue with exploitable details.
