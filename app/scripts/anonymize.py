#!/usr/bin/env python3
"""
Anonymization script for finance automation data.

This script:
1. Generates new anonymous CIDs, mobiles, references, and names
2. Keeps amounts and dates unchanged
3. Creates a mapping file for reference
4. Outputs anonymized data to a new database or CSV files
"""

import argparse
import hashlib
import json
import secrets
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from faker import Faker
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.db.session import engine, async_session_maker
from app.models import Contract, Installment, Contact, Upload, ContractClosure, Notification, AuditLog

setup_logging()
logger = get_logger(__name__)

fake = Faker()


class Anonymizer:
    """Handles anonymization of sensitive data while preserving amounts and dates."""

    def __init__(self, salt: Optional[str] = None):
        self.salt = salt or settings.ANONYMIZATION_SALT
        self.cid_map: Dict[str, str] = {}
        self.mobile_map: Dict[str, str] = {}
        self.reference_map: Dict[str, str] = {}
        self.customer_map: Dict[str, str] = {}
        self.email_map: Dict[str, str] = {}

    def _hash_value(self, value: str) -> str:
        """Create a deterministic hash for consistent mapping."""
        return hashlib.sha256(f"{self.salt}:{value}".encode()).hexdigest()[:16]

    def anonymize_cid(self, original_cid: str) -> str:
        """Generate anonymous CID."""
        if original_cid not in self.cid_map:
            # Format: CID-XXXXXXXX
            hash_suffix = self._hash_value(original_cid)[:8].upper()
            self.cid_map[original_cid] = f"CID-{hash_suffix}"
        return self.cid_map[original_cid]

    def anonymize_mobile(self, original_mobile: str) -> str:
        """Generate anonymous mobile number."""
        if original_mobile not in self.mobile_map:
            # Format: +91-XXXXXXXXXX (Indian format)
            hash_suffix = self._hash_value(original_mobile)[:10]
            # Ensure it looks like a valid mobile
            self.mobile_map[original_mobile] = f"+91-{hash_suffix[:5]}{hash_suffix[5:]}"
        return self.mobile_map[original_mobile]

    def anonymize_reference(self, original_reference: str) -> str:
        """Generate anonymous reference."""
        if original_reference not in self.reference_map:
            # Format: REF-XXXXXXXX
            hash_suffix = self._hash_value(original_reference)[:8].upper()
            self.reference_map[original_reference] = f"REF-{hash_suffix}"
        return self.reference_map[original_reference]

    def anonymize_customer(self, original_customer: str) -> str:
        """Generate anonymous customer name."""
        if original_customer not in self.customer_map:
            # Generate fake name but keep deterministic
            seed = int(self._hash_value(original_customer), 16) % (2**32)
            fake.seed_instance(seed)
            self.customer_map[original_customer] = fake.name()
        return self.customer_map[original_customer]

    def anonymize_email(self, original_email: str) -> str:
        """Generate anonymous email."""
        if original_email not in self.email_map:
            local, domain = original_email.split("@") if "@" in original_email else (original_email, "example.com")
            hash_suffix = self._hash_value(local)[:8]
            self.email_map[original_email] = f"user{hash_suffix}@anon.{domain}"
        return self.email_map[original_email]

    def anonymize_brand(self, original_brand: str) -> str:
        """Generate anonymous brand name."""
        seed = int(self._hash_value(original_brand), 16) % (2**32)
        fake.seed_instance(seed)
        return fake.company()

    def anonymize_region(self, original_region: str) -> str:
        """Generate anonymous region."""
        seed = int(self._hash_value(original_region), 16) % (2**32)
        fake.seed_instance(seed)
        return fake.state()

    def save_mapping(self, output_path: Path) -> None:
        """Save the anonymization mapping to a JSON file."""
        mapping = {
            "cid_map": self.cid_map,
            "mobile_map": self.mobile_map,
            "reference_map": self.reference_map,
            "customer_map": self.customer_map,
            "email_map": self.email_map,
        }
        with open(output_path, "w") as f:
            json.dump(mapping, f, indent=2)
        logger.info(f"Saved anonymization mapping to {output_path}")

    async def anonymize_database(self, session: AsyncSession, output_dir: Path) -> None:
        """Anonymize all data in the database and export to CSV files."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # Anonymize contracts
        logger.info("Anonymizing contracts...")
        result = await session.execute(select(Contract))
        contracts = result.scalars().all()

        contracts_data = []
        for contract in contracts:
            contracts_data.append({
                "id": contract.id,
                "reference": self.anonymize_reference(contract.reference),
                "item": contract.item,
                "brand": self.anonymize_brand(contract.brand) if contract.brand else None,
                "region": self.anonymize_region(contract.region) if contract.region else None,
                "cost_center": contract.cost_center,
                "ministry_agency": contract.ministry_agency,
                "payment_type": contract.payment_type,
                "emi_months": contract.emi_months,
                "customer": self.anonymize_customer(contract.customer) if contract.customer else None,
                "cid": self.anonymize_cid(contract.cid) if contract.cid else None,
                "mobile": self.anonymize_mobile(contract.mobile) if contract.mobile else None,
                "contract_date": contract.contract_date.isoformat() if contract.contract_date else None,
                "start_date": contract.start_date.isoformat() if contract.start_date else None,
                "end_date": contract.end_date.isoformat() if contract.end_date else None,
                "monthly_deduction": float(contract.monthly_deduction) if contract.monthly_deduction else None,
                "sales_amount": float(contract.sales_amount) if contract.sales_amount else None,
                "gst": float(contract.gst) if contract.gst else None,
                "state": contract.state.value,
                "created_at": contract.created_at.isoformat() if contract.created_at else None,
                "updated_at": contract.updated_at.isoformat() if contract.updated_at else None,
            })

        import csv
        with open(output_dir / "contracts_anonymized.csv", "w", newline="") as f:
            if contracts_data:
                writer = csv.DictWriter(f, fieldnames=contracts_data[0].keys())
                writer.writeheader()
                writer.writerows(contracts_data)
        logger.info(f"Exported {len(contracts_data)} anonymized contracts")

        # Anonymize installments (keep amounts and dates, only link to anonymized contracts)
        logger.info("Anonymizing installments...")
        result = await session.execute(select(Installment))
        installments = result.scalars().all()

        installments_data = []
        for inst in installments:
            installments_data.append({
                "id": inst.id,
                "contract_id": inst.contract_id,  # Keep original FK for now
                "due_month": inst.due_month.isoformat() if inst.due_month else None,
                "due_amount": float(inst.due_amount),
                "received_amount": float(inst.received_amount),
                "salary_amount": float(inst.salary_amount) if inst.salary_amount else None,
                "status": inst.status.value,
                "created_at": inst.created_at.isoformat() if inst.created_at else None,
                "updated_at": inst.updated_at.isoformat() if inst.updated_at else None,
            })

        with open(output_dir / "installments_anonymized.csv", "w", newline="") as f:
            if installments_data:
                writer = csv.DictWriter(f, fieldnames=installments_data[0].keys())
                writer.writeheader()
                writer.writerows(installments_data)
        logger.info(f"Exported {len(installments_data)} anonymized installments")

        # Anonymize contacts
        logger.info("Anonymizing contacts...")
        result = await session.execute(select(Contact))
        contacts = result.scalars().all()

        contacts_data = []
        for contact in contacts:
            contacts_data.append({
                "id": contact.id,
                "cid": self.anonymize_cid(contact.cid),
                "email": self.anonymize_email(contact.email) if contact.email else None,
                "mobile": self.anonymize_mobile(contact.mobile) if contact.mobile else None,
                "source": contact.source,
                "last_synced_at": contact.last_synced_at.isoformat() if contact.last_synced_at else None,
                "history": contact.history,
                "created_at": contact.created_at.isoformat() if contact.created_at else None,
                "updated_at": contact.updated_at.isoformat() if contact.updated_at else None,
            })

        with open(output_dir / "contacts_anonymized.csv", "w", newline="") as f:
            if contacts_data:
                writer = csv.DictWriter(f, fieldnames=contacts_data[0].keys())
                writer.writeheader()
                writer.writerows(contacts_data)
        logger.info(f"Exported {len(contacts_data)} anonymized contacts")

        # Export other tables as-is (they don't contain PII)
        for table_name, model in [
            ("uploads", Upload),
            ("contract_closures", ContractClosure),
            ("notifications", Notification),
            ("audit_log", AuditLog),
        ]:
            logger.info(f"Exporting {table_name}...")
            result = await session.execute(select(model))
            records = result.scalars().all()
            data = [self._model_to_dict(r) for r in records]

            with open(output_dir / f"{table_name}_anonymized.csv", "w", newline="") as f:
                if data:
                    writer = csv.DictWriter(f, fieldnames=data[0].keys())
                    writer.writeheader()
                    writer.writerows(data)
            logger.info(f"Exported {len(data)} {table_name} records")

        # Save mapping
        self.save_mapping(output_dir / "anonymization_mapping.json")
        logger.info("Anonymization complete!")

    def _model_to_dict(self, model) -> Dict[str, Any]:
        """Convert SQLAlchemy model to dict."""
        data = {}
        for column in model.__table__.columns:
            value = getattr(model, column.name)
            if isinstance(value, (date,)):
                data[column.name] = value.isoformat()
            elif isinstance(value, Decimal):
                data[column.name] = float(value)
            elif hasattr(value, "value"):  # Enum
                data[column.name] = value.value
            else:
                data[column.name] = value
        return data


async def main():
    parser = argparse.ArgumentParser(description="Anonymize finance automation data")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./anonymized_data"),
        help="Output directory for anonymized data",
    )
    parser.add_argument(
        "--salt",
        type=str,
        help="Salt for deterministic anonymization (defaults to ANONYMIZATION_SALT from env)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be anonymized without writing files",
    )
    args = parser.parse_args()

    anonymizer = Anonymizer(salt=args.salt)

    if args.dry_run:
        logger.info("DRY RUN - No files will be written")
        # Just show sample mappings
        sample_data = ["CID12345", "9876543210", "REF-ABC-123", "John Doe", "john@example.com"]
        for item in sample_data:
            if item.startswith("CID") or item.isdigit():
                print(f"  {item} -> {anonymizer.anonymize_cid(item)}")
            elif "@" in item:
                print(f"  {item} -> {anonymizer.anonymize_email(item)}")
            elif item.startswith("REF"):
                print(f"  {item} -> {anonymizer.anonymize_reference(item)}")
            else:
                print(f"  {item} -> {anonymizer.anonymize_customer(item)}")
        return

    async with async_session_maker() as session:
        await anonymizer.anonymize_database(session, args.output_dir)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())