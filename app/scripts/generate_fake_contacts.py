#!/usr/bin/env python3
"""
Generate fake contacts file with made-up emails for testing.

This script creates a CSV file with fake contact data that can be used
for testing the contacts import functionality.
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import List

from faker import Faker

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.logging import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

fake = Faker(["en_IN"])  # Indian locale for realistic names


def generate_fake_contacts(count: int, output_path: Path) -> List[dict]:
    """Generate fake contacts data."""
    contacts = []

    for i in range(count):
        # Generate a realistic CID format
        cid = f"CID{fake.random_number(digits=8, fix_len=True)}"

        # Generate name and derive email from it
        name = fake.name()
        first_name = name.split()[0].lower()
        last_name = name.split()[-1].lower() if len(name.split()) > 1 else ""

        # Create realistic email variations
        email_domains = [
            "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
            "company.com", "corp.in", "gov.in", "nic.in"
        ]
        domain = fake.random_element(email_domains)

        email_patterns = [
            f"{first_name}.{last_name}@{domain}",
            f"{first_name}{last_name}@{domain}",
            f"{first_name}_{last_name}@{domain}",
            f"{first_name}{fake.random_number(digits=3)}@{domain}",
            f"{first_name[0]}{last_name}@{domain}",
        ]
        email = fake.random_element(email_patterns)

        # Generate Indian mobile number
        mobile = f"+91-{fake.random_element(['7', '8', '9'])}{fake.random_number(digits=9, fix_len=True)}"

        # Source of contact
        sources = ["manual", "import", "api", "portal", "bulk_upload"]
        source = fake.random_element(sources)

        contact = {
            "cid": cid,
            "name": name,
            "email": email,
            "mobile": mobile,
            "source": source,
            "notes": fake.sentence(nb_words=6) if fake.boolean(chance_of_getting_true=30) else "",
        }
        contacts.append(contact)

    return contacts


def write_contacts_csv(contacts: List[dict], output_path: Path) -> None:
    """Write contacts to CSV file."""
    fieldnames = ["cid", "name", "email", "mobile", "source", "notes"]

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(contacts)

    logger.info(f"Generated {len(contacts)} fake contacts to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate fake contacts CSV file")
    parser.add_argument(
        "-n", "--count",
        type=int,
        default=100,
        help="Number of contacts to generate (default: 100)"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("./fake_contacts.csv"),
        help="Output CSV file path (default: ./fake_contacts.csv)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Random seed for reproducible generation"
    )
    args = parser.parse_args()

    if args.seed:
        fake.seed_instance(args.seed)
        logger.info(f"Using seed: {args.seed}")

    contacts = generate_fake_contacts(args.count, args.output)
    write_contacts_csv(contacts, args.output)

    # Print sample
    logger.info("Sample contacts:")
    for contact in contacts[:5]:
        logger.info(f"  {contact['cid']} | {contact['name']} | {contact['email']} | {contact['mobile']}")


if __name__ == "__main__":
    main()