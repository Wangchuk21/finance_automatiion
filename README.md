# Finance Automation

A FastAPI-based application for managing contracts, installments, and customer communications for finance automation.

## Features

- **Contract Management**: Track contracts with references, customers, financial details, and states
- **Installment Tracking**: Monitor due/received amounts per contract per month
- **Upload Processing**: Handle file uploads with checksums, status tracking, and rollback support
- **Contact Management**: Store and sync customer contact information
- **Notifications**: Template-based email/SMS notifications
- **Audit Logging**: Complete audit trail for all important actions
- **Data Anonymization**: Built-in script to anonymize PII while preserving financial data

## Tech Stack

- **Framework**: FastAPI 0.115+
- **Database**: PostgreSQL 16 with SQLAlchemy 2.0 (async)
- **Migrations**: Alembic
- **Validation**: Pydantic v2
- **Logging**: Structured JSON logging
- **Testing**: pytest + pytest-asyncio

## Quick Start

### 1. Start PostgreSQL

```bash
docker-compose up -d postgres
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 4. Run Migrations

```bash
alembic upgrade head
```

### 5. Start Application

```bash
uvicorn app.main:app --reload
```

Visit http://localhost:8000/docs for API documentation.

## Project Structure

```
finance_automation/
├── alembic/              # Database migrations
│   ├── versions/         # Migration files
│   └── env.py           # Alembic environment
├── app/
│   ├── api/             # API routes (to be implemented)
│   ├── core/            # Core configuration
│   │   ├── config.py    # Pydantic settings
│   │   └── logging.py   # JSON logging setup
│   ├── db/              # Database session management
│   │   └── session.py   # Async engine and session
│   ├── models/          # SQLAlchemy models
│   │   └── __init__.py  # All table definitions
│   ├── schemas/         # Pydantic schemas (to be implemented)
│   └── scripts/         # Utility scripts
│       ├── anonymize.py           # Data anonymization
│       └── generate_fake_contacts.py  # Test data generation
├── tests/               # Test files
├── .env                 # Environment variables (not in git)
├── .env.example         # Example environment file
├── alembic.ini          # Alembic configuration
├── docker-compose.yml   # PostgreSQL + pgAdmin
├── pyproject.toml       # Project configuration
└── requirements.txt     # Python dependencies
```

## Database Schema

### Core Tables

| Table | Description |
|-------|-------------|
| `contracts` | Main contract records with financial details |
| `installments` | Monthly installments per contract |
| `installment_history` | Status change history per upload |
| `uploads` | File upload tracking with checksums |
| `contract_closures` | Contract closure records |
| `contacts` | Customer contact information |
| `notifications` | Sent notifications |
| `notification_templates` | Notification templates |
| `users` | System users |
| `audit_log` | Audit trail |

### Contract States

- `active` - Normal active contract
- `missing_review` - Requires review
- `closed` - Contract closed
- `reopened` - Previously closed, now active

### Installment Statuses

- `pending` - Not yet due
- `partial` - Partially paid
- `paid` - Fully paid
- `overdue` - Past due date
- `waived` - Waived off

### Upload Statuses

- `pending` - Uploaded, awaiting confirmation
- `confirmed` - Confirmed and applied
- `rolled_back` - Reverted

## Utility Scripts

### Generate Fake Contacts

```bash
python -m app.scripts.generate_fake_contacts -n 500 -o ./fake_contacts.csv --seed 42
```

### Anonymize Data

```bash
# Export anonymized CSV files
python -m app.scripts.anonymize --output-dir ./anonymized_data

# Dry run to see mappings
python -m app.scripts.anonymize --dry-run
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | Async PostgreSQL connection string | Yes |
| `DATABASE_URL_SYNC` | Sync PostgreSQL connection for Alembic | Yes |
| `SECRET_KEY` | JWT secret key (min 32 chars) | Yes |
| `ANONYMIZATION_SALT` | Salt for deterministic anonymization | Yes |
| `APP_ENV` | Environment (development/production) | No |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | No |
| `SMTP_*` | Email configuration | No |

## Development

### Code Style

```bash
ruff check .
ruff format .
```

### Run Tests

```bash
pytest -v
```

### Create Migration

```bash
alembic revision --autogenerate -m "description"
```

### Apply Migrations

```bash
alembic upgrade head
```

## Production Deployment

1. Set `APP_ENV=production` and `DEBUG=false`
2. Use strong `SECRET_KEY` and `ANONYMIZATION_SALT`
3. Configure proper `DATABASE_URL` with connection pooling
4. Set up SMTP for notifications
5. Use a reverse proxy (nginx) with SSL
6. Run with gunicorn: `gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker`

## License

Internal use only.