<div align="center">
  <img src="assets/logo.png" alt="FYT Data Management logo" width="128" height="128" />
  <h1>FYT Data Management</h1>
  <p>A desktop and web workspace for manufacturing operations, business data processing, and daily management.</p>
  <p>
    <a href="README.zh-CN.md">简体中文</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.10--3.13-3776AB?logo=python&logoColor=white" alt="Python 3.10-3.13" />
    <img src="https://img.shields.io/badge/React-19.2-61DAFB?logo=react&logoColor=20232A" alt="React 19.2" />
    <img src="https://img.shields.io/badge/Vite-8.1-646CFF?logo=vite&logoColor=white" alt="Vite 8.1" />
    <img src="https://img.shields.io/badge/Tauri-2.11-FFC131?logo=tauri&logoColor=black" alt="Tauri 2.11" />
  </p>
  <p>
    <img src="https://img.shields.io/badge/Rust-stable-000000?logo=rust&logoColor=white" alt="Rust stable" />
    <img src="https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white" alt="SQLite" />
    <img src="https://img.shields.io/badge/Docker-optional-2496ED?logo=docker&logoColor=white" alt="Docker optional" />
    <img src="https://img.shields.io/badge/License-MIT-2EA44F" alt="MIT License" />
  </p>
</div>

> Turn scattered Excel files, PDFs, folders, and manual steps into a reviewable, traceable, and collaborative workflow.

Current version: `v1.3.0`

## Overview

FYT Data Management is an enterprise-oriented data workspace for attendance, material arrivals, procurement, reconciliation, invoicing, production data, shop-floor issues, and daily management.

The typical workflow is:

```text
Upload files → recognize and analyze → review manually → inspect results online → download reports
```

Business processing works on uploaded copies by default, so the original files are not modified directly.

The project supports three usage modes:

- **Windows desktop application** — for individual or office-based file processing.
- **Web application** — for LAN or internal multi-user collaboration.
- **Mobile browser** — optimized for taking photos, submitting, reviewing, and closing shop-floor issues.

## Feature map

| Area | Main capabilities |
| --- | --- |
| Human resources | Attendance entry, monthly attendance archives, working-hour reconciliation |
| Materials and production | Daily material arrivals, delivery plans, shipping review comparisons, production data |
| Procurement and suppliers | Procurement reconciliation, supplier batch sheets, purchase-plan imports, variance lists, statement generation |
| Sales and finance | Sales pivots, invoice statistics, invoice-to-shipment matching, amount capitalization |
| Daily management and collaboration | Daily dashboard, shop-floor issues, notices and action items, task center, message center |
| Data governance | Team file library, master-data learning, conflict review, file classification, recycle bin |
| File utilities | Batch renaming, text tools, PDF tools, Excel tools, and table comparison |

Where applicable, completed business tasks display key metrics, details, variances, confidence information, and review hints directly in the application. Formal Excel and PDF reports remain available for download.

## Highlights

### One workflow for business files

Users can adjust dates, tolerances, and statistical options before processing. For workflows that need confirmation, the system returns an analysis plan first and only generates the formal result after manual confirmation.

### Online results and formal reports

Web and desktop views show structured results for quick review. Excel and PDF files remain available when a report needs to be archived, shared, or processed further.

### Continuous master-data governance

Administrators can upload new business tables so the system can learn relationships between materials, suppliers, and fields. Conflicts are surfaced for review instead of silently overwriting confirmed master data.

### Mobile shop-floor workflow

Shop-floor issues support photos, text fields, responsible people, notes, editing after publication, resolution updates, and date-range exports.

## Account roles

Web registration requires administrator approval.

| Role | Main permissions |
| --- | --- |
| Member | Workbench, business modules, tasks, messages, and submitting/viewing shop-floor issues |
| Team leader | Member capabilities plus team database access and maintenance of self-published issues |
| Administrator | Daily dashboard, report center, account review, role management, master-data maintenance, and all issue records |

The server enforces the same permissions again for API requests, task ownership, uploaded files, and generated results.

## Technology stack

| Layer | Technology |
| --- | --- |
| Shared business core | Python 3.10–3.13, Excel/PDF processing, SQLite |
| Web frontend | React 19.2, TypeScript 7, Vite 8.1 |
| Desktop application | Tauri 2.11, Rust stable, React |
| Web server | Python standard-library HTTP server, SQLite, systemd |
| Optional deployment | Docker Compose, Caddy reverse proxy, Cloudflare Origin CA |

## Supported files

- Excel: `.xlsx`, `.xlsm`, `.xls`, `.csv`
- PDF: invoice recognition, merging, splitting, and page extraction
- Images: shop-floor issue uploads with multiple images per issue

Supported formats vary by business module. Follow the file-type guidance shown on the selected page.

## Deployment commands

### Linux: deploy from the public Git repository

```bash
sudo dnf install -y curl ca-certificates && curl -fsSL https://raw.githubusercontent.com/KuroNeko-night/fyt-data-mgmt/main/packaging/linux/deploy-from-git.sh | sudo bash
```

### Linux: install from a deployment package

```bash
sudo unzip fyt-server-linux-v1.3.0.zip -d /opt/fyt
cd /opt/fyt/fyt-server-linux-v1.3.0
sudo bash install.sh
```

### Docker

```bash
umask 077
mkdir -p secrets
{ printf 'Aa1'; openssl rand -hex 16; } > secrets/admin-password.local.txt
FYT_ADMIN_PASSWORD_FILE=../secrets/admin-password.local.txt docker compose -f docker/docker-compose.yml up -d --build
```

### Windows: build a server package

```powershell
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe scripts\build_deploy.py
```

### Tauri: build the desktop installer

```powershell
npm --prefix tauri-app ci
npm --prefix tauri-app run tauri:build
```

## Data and security

- Accounts, uploads, task results, and personal settings are isolated by user.
- Registered accounts require administrator approval and passwords must meet the configured security policy.
- Changing a password, revoking a device, or resetting an account invalidates affected sessions.
- Administrators can manage backups, recovery, and the recycle bin.
- Public deployments should use HTTPS, a configured domain, a reverse proxy, and access controls.
- Do not commit administrator passwords, private keys, tokens, account databases, or real business files.

## Common questions

### Does processing modify the original file?

No. Processing uses an uploaded copy and saves generated results as new files.

### Why does some processing require manual review?

Business files may contain merged cells, non-standard headers, notes, and historical template variations. Review confirms recognized dates, batches, suppliers, and matching relationships before the formal output is generated.

### Can the Web application be used on a phone?

Yes. Most pages support mobile browsers, and the shop-floor issue workflow is specifically optimized for phone cameras and portrait screens.

### What should I do if I forget my password?

Contact an administrator for a normal account reset. Administrator resets should use the controlled deployment or maintenance procedure; never post passwords, databases, certificates, or private keys in public issues.

## License

This project is released under the [MIT License](LICENSE).

Copyright © 2026 KuroNeko-night
