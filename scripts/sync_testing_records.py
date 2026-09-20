#!/usr/bin/env python3
"""Refresh customer-safe batch summaries from a private source-page URL."""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup


PRODUCT_ALIASES = {
    "5-Amino-1MQ 50 mg": "5-amino-1mq 50mg",
    "BAC Water 10 mL": "bac 10ml",
    "Epitalon 50 mg": "epitalon 50mg",
    "Melanotan 2 10 mg": "melanotan 2 10mg",
    "IllumiNeuro": "illumineuro",
    "PT-141 10 mg": "pt141 10mg",
    "TB4 10 mg": "tb4 10mg",
    "BPC-157 10 mg": "bpc157 10mg",
    "NAD+ 500": "nad+ 500",
    "KLOW": "klow",
    "NAD+ 1000": "nad+ 1000",
    "Cartalax 40 mg": "cartalax 40mg",
    "Cartalax / TB4 / BPC-157 10/5/5": "cartalax/tb4",
    "GHK / KPV 50/20": "ghk/kpv 50/20",
    "CJC / IPA 10/10": "cjc/ipa 10/10",
    "Thymosin Alpha-1 10 mg": "thymosin a1 10mg",
    "KPV 30 mg": "kpv 30mg",
    "Tesamorelin 10 mg": "tesa 10mg",
    "Tesamorelin 20 mg": "tesa 20mg",
    "GHK 100 mg": "ghk 100mg",
    "Tirzepatide 30 mg": "tirz 30mg",
    "Tirzepatide 60 mg": "tirz 60mg",
    "BPC-157 / TB4 10/10": "bpc/tb4 10/10",
    "NA Semax Amidate 10 mg": "na semax amidate 10mg",
    "NA Selank Amidate 10 mg": "na selank amidate 10mg",
    "MOTS-C 40 mg": "mots-c 40mg",
    "Tesamorelin / Ipamorelin 10/3 mg": "tesa/ ipa 10/3mg",
    "GLOW 70 mg": "glow 70mg",
}

TEST_NAMES = {
    "purity": "Purity / content",
    "h-metals": "Heavy metals",
    "heavy metals": "Heavy metals",
    "endotoxin": "Endotoxin",
    "benzyl": "Benzyl alcohol",
}


def clean(value: str) -> str:
    return " ".join(value.split()).strip()


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def download(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "StonePointTestingSync/1.0 (+https://stonepointpeptides.com)"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read()


def extract_cards(document: bytes) -> list[dict[str, object]]:
    soup = BeautifulSoup(document, "html.parser")
    found: list[dict[str, object]] = []
    for card in soup.select("div.card"):
        name_node = card.find("p")
        if not name_node:
            continue
        batch_node = next(
            (node for node in card.find_all(["h5", "h6"]) if "Batch:" in node.get_text(" ", strip=True)),
            None,
        )
        if not batch_node:
            continue
        batch = clean(batch_node.get_text(" ", strip=True).split("Batch:", 1)[1])
        tests: list[str] = []
        for button in card.select("a.elementor-button"):
            label = normalize(button.get_text(" ", strip=True))
            if label in TEST_NAMES and TEST_NAMES[label] not in tests:
                tests.append(TEST_NAMES[label])
        if tests:
            found.append({"name": normalize(name_node.get_text(" ", strip=True)), "batch": batch, "tests": tests})
    return found


def build_records(cards: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    records: dict[str, list[dict[str, object]]] = {}
    missing: list[str] = []
    for product, alias in PRODUCT_ALIASES.items():
        matches = [card for card in cards if card["name"] == alias]
        if not matches:
            missing.append(product)
            continue
        chosen = matches[-1]
        batch = str(chosen["batch"])
        # The source heading has historically omitted the "2" in this lot,
        # while all three associated lab-record identifiers contain TE20.
        if product == "Tesamorelin 20 mg" and batch == "TE10-0626":
            batch = "TE20-0626"
        records[product] = [{
            "label": "Testing summary",
            "lot": batch,
            "file": f"testing-records.html#{slugify(product)}",
            "tests": chosen["tests"],
            "availability": "Full reports available by request",
        }]
    if missing:
        raise RuntimeError("Missing catalog matches: " + ", ".join(missing))
    return records


def write_manifest(records: dict[str, list[dict[str, object]]], destination: Path) -> None:
    payload = json.dumps(records, indent=2, ensure_ascii=False)
    destination.write_text(
        "/* Generated customer-safe testing index. Source URLs are intentionally omitted. */\n"
        f"window.STONE_POINT_COAS = {payload};\n",
        encoding="utf-8",
    )


def main() -> int:
    source_url = os.environ.get("RESULTS_SOURCE_URL", "").strip()
    if not source_url:
        print("RESULTS_SOURCE_URL is required", file=sys.stderr)
        return 2
    cards = extract_cards(download(source_url))
    records = build_records(cards)
    output = Path(__file__).resolve().parents[1] / "coa-library.js"
    write_manifest(records, output)
    print(f"Updated {len(records)} customer-safe testing summaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
