# PDF Report Generator

Python service that renders a JSON payload into a PDF report using a visual
template editor and a ReportLab-based engine. Runs as a Kubernetes job (Argo
Workflows), uploads the result to Cloudflare R2, and notifies experiment-manager
via webhook.

## Quick Start

```bash
# Install dependencies
uv sync

# Generate PDF locally (writes to output.pdf)
DATA_JSON=mock/data/1.json COMPONENTS_JSON=mock/pdf/1.json PDF_OUTPUT=output.pdf \
  uv run python -m src

# Open the visual template editor
uv run python -m src --editor
# → http://localhost:8765

# Run tests
make test
```

## Environment Variables

### Core (required)

| Variable | Description |
|----------|-------------|
| `DATA_JSON` | Experiment data — inline JSON string or path to `.json` file |
| `COMPONENTS_JSON` | PDF template components — inline JSON string or path to `.json` file |
| `PDF_OUTPUT` | Local output path (used only when R2 is not configured) |

### R2 storage (required in production)

| Variable | Description |
|----------|-------------|
| `S3_BUCKET` | R2 bucket name |
| `S3_ENDPOINT` | `https://<account-id>.r2.cloudflarestorage.com` |
| `S3_ACCESS_KEY` | R2 API token key ID |
| `S3_SECRET_KEY` | R2 API token secret |
| `S3_REGION` | Optional, defaults to `auto` |

When `S3_BUCKET` is set, the generated PDF is uploaded to R2 under
`pdfs/{exp_tmpl_id}/{timestamp}.pdf` and no local file is written.

### Webhook (required in production)

| Variable | Description |
|----------|-------------|
| `WEBHOOK_URL` | Base URL of experiment-manager (e.g. `https://api.internal`) |

After generation the service POSTs to
`{WEBHOOK_URL}/api/experiments/{exp_tmpl_id}/report` with the R2 key and
timestamp. Retries 3× on failure.

## Input shape

```json
{
  "exp_tmpl_id": "uuid-of-the-experiment-template",
  "template": "{{full_name}} — {{plan}}",

  "userForm":   { "questions": [{"id": "full_name", "default": "Alice"}] },
  "workerForm": { "questions": [...] },
  "calculations": { "delta_T": 4.2 }
}
```

`COMPONENTS_JSON` is a separate array of component objects (stored in
`pdf_templates.components` in the DB).

## Project Layout

```
src/
  engine/       pure rendering core — zero rendering deps
  r2.py         Cloudflare R2 upload + presign helpers
  output.py     PDF rendering (ReportLab)
  config.py     Config dataclasses; reads .env
  __main__.py   CLI entry point

src/editor/     dev-only visual editor (FastAPI + JS); safe to delete
mock/data/      sample experiment JSON payloads
mock/pdf/       sample component arrays
```

`editor/` is fully optional — deleting it does not affect PDF generation.
