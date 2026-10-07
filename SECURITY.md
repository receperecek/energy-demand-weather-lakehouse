# Security policy

Do not post credentials in issues, notebooks, screenshots or pull requests. Report a suspected vulnerability using GitHub's [private vulnerability reporting](https://github.com/receperecek/energy-demand-weather-lakehouse/security/advisories/new), without including a live secret in the initial message.

## Credential boundaries

- EIA credentials reside in a Databricks-backed secret scope with an explicitly restricted principal. Use `dbutils.secrets.get` in the job. Workspace administrators and authorized scope managers remain privileged; secret redaction is not an access-control boundary.
- Local Databricks access uses OAuth through a named CLI profile. Do not copy `.databrickscfg`, token caches or exported access tokens into the project.
- A local standalone ingestion command reads `EIA_API_KEY` from its process environment. `.env.example` contains placeholders only. Keep any actual local secret file outside the repository.
- GitHub CI runs contract tests without source credentials. It has read-only repository permissions and does not deploy into a personal workspace.
- Source request URLs and original exceptions are not printed. EIA request echoes and sensitive fields are removed before snapshots are written. Snapshot hashes apply to sanitized content.

## Before publishing

Inspect staged paths, scan tracked content and full reachable Git history, and verify the actual secret is absent without printing it. Review notebooks, images, generated reports, dbt artifacts and deployment state as well as source code. `.gitignore` does not remove a secret already committed. Only attributed aggregate evidence intended for publication belongs in the repository; full raw dumps and private lessons do not.

The built-in scanner catches forbidden paths, common credential formats and long assignments. Pattern scanners can miss an unusual secret or produce false positives: they complement a staged-file review and exact-value check, rather than proving perfect security.

## Exposure response

Revoke or regenerate the affected credential at its provider, update the secret scope, suspend dependent runs if necessary, and investigate access. Remove the exposure from files and history, but do not assume rewriting Git removes copies or logs. Never test whether an exposed key still works by publishing it again.
