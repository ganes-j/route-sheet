#!/usr/bin/env python3

import json
import random
from pathlib import Path


SEED = 20261125
VOCABULARY = ("name", "email", "phone", "ssn", "address", "dob", "card")
NAMES = ("Maren Quill", "Tovin Ember", "Liora Fen", "Sable Rowan", "Niko Vale")
EMAILS = (
    "maren.quill@example.com",
    "tovin.ember@example.org",
    "liora.fen@example.net",
    "sable.rowan@example.com",
    "niko.vale@example.org",
)
STREETS = ("7 Lantern Way", "42 Juniper Orbit", "18 Copper Finch Road", "63 Moonpetal Lane")
DATES = ("1988-03-14", "1991-11-02", "1976-06-23", "2000-01-19")
CARDS = ("4111 1111 1111 1111", "5555 5555 5555 4444")


def _prompt(snippet):
    return (
        "Classify personal PII in the snippet. Company contact details and identifier-like "
        "values explicitly described as non-personal are not personal PII. Reply with only "
        "a JSON object with exactly the keys contains_pii and pii_types. contains_pii must be "
        "true or false. pii_types must be an alphabetically sorted list drawn only from "
        f"{list(VOCABULARY)}. Snippet: {snippet}"
    )


def generate_items():
    rng = random.Random(SEED)
    names = rng.sample(NAMES, len(NAMES))
    emails = rng.sample(EMAILS, len(EMAILS))
    streets = rng.sample(STREETS, len(STREETS))
    dates = rng.sample(DATES, len(DATES))
    phone_numbers = [f"555-{number:04d}" for number in rng.sample(range(100, 200), 3)]
    ssns = [f"9{number:02d}-{middle:02d}-{last:04d}" for number, middle, last in (
        (12, 34, 6789),
        (43, 21, 2468),
        (76, 54, 1357),
    )]

    records = [
        (f"Send the proof to {names[0]} at {emails[0]}.", ["email", "name"]),
        (f"The personal callback number is {phone_numbers[0]}.", ["phone"]),
        (f"The applicant's synthetic SSN is {ssns[0]}.", ["ssn"]),
        (f"Deliver to the resident at {streets[0]}, Northglass, ZZ 00000.", ["address"]),
        (f"{names[1]} confirmed their date of birth is {dates[0]}.", ["dob", "name"]),
        (f"Use the card on the customer's test profile: {CARDS[0]}.", ["card"]),
        (
            f"For {names[2]}, call {phone_numbers[1]} before visiting {streets[1]}, "
            "Northglass, ZZ 00000.",
            ["address", "name", "phone"],
        ),
        (f"The member login is {emails[1]} and the synthetic SSN is {ssns[1]}.", ["email", "ssn"]),
        (f"The patient intake form lists DOB {dates[1]} but no name.", ["dob"]),
        (f"{names[3]}'s test payment card is {CARDS[1]}.", ["card", "name"]),
        ("Forecast issued 2026-11-25: rain begins after 18:00.", []),
        (f"Warehouse SKU {phone_numbers[2]} is on shelf 12; it is not a telephone number.", []),
        (f"Fictional company Northglass Works receives freight at {streets[2]}, Northglass, ZZ 00000; no person resides there.", []),
        ("Version 3.8 launches on 2027-02-04; that date is not anyone's birthday.", []),
        ("Use support@example.net for the fictional company help desk; it is not a person's mailbox.", []),
        (f"Batch code {ssns[2]} resembles an SSN but is explicitly a machine-lot identifier.", []),
        (f"The payment integration guide uses {CARDS[0]} as a public test value, not a customer's card.", []),
        ("Sensor coordinates are 41.2033, -77.1945 and altitude is 620 meters.", []),
        ("Invoice FABLE-204 totals USD 1,284.50 for twelve ceramic bearings.", []),
        ("Meet in room C-14 on 2026-12-03; the room code and meeting date identify no person.", []),
    ]

    items = []
    for index, (snippet, pii_types) in enumerate(records, start=1):
        sorted_types = sorted(pii_types)
        items.append(
            {
                "id": f"pii-{index:02d}",
                "prompt": _prompt(snippet),
                "expected": {
                    "contains_pii": bool(sorted_types),
                    "pii_types": sorted_types,
                },
            }
        )
    return items


def write_fixture(path=None):
    destination = Path(path) if path else Path(__file__).resolve().parent / "fixtures" / "pii-classification.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in generate_items())
    destination.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    write_fixture()
