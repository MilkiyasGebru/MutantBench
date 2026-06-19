"""Audit and optionally remove redundant Kintis mutant records in dataset.ttl.

Kintis mutants were ingested twice: once with schema:contributor (convert.py)
and again with schema:citation. When both records share the same equivalence
label and no other source disagrees, the contributor record is redundant.

Groups with a conflicting Houshmand label (e.g. Kintis EQ vs Houshmand NEQ)
are intentionally skipped.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

DATASET = Path(__file__).resolve().parent / 'dataset.ttl'
KINTIS = 'kintis2016analysing'
HOUSHMAND = 'houshmand2017tce'


def normalize_diff(diff: str) -> str:
    lines = [
        line for line in diff.strip().split('\n')
        if line.startswith('-') or line.startswith('+')
    ]
    return '\n'.join(sorted(lines))


def parse_mutant_blocks(content: str) -> list[tuple[str, dict]]:
    blocks = re.split(r'\n(?=<mb:mutant#)', content)
    records = []
    for block in blocks:
        mutant_id = re.search(r'<mb:mutant#([^>]+)>', block)
        if not mutant_id:
            continue
        diff_match = re.search(r'mb:difference """(.*?)"""', block, re.DOTALL)
        program_match = re.search(r'mb:program <mb:program#([^>]+)>', block)
        citation = re.search(r'schema:citation <mb:paper#([^>]+)>', block)
        contributor = re.search(r'schema:contributor <mb:paper#([^>]+)>', block)
        equiv = re.search(r'mb:equivalence "([^"]+)"', block)
        if not diff_match or not program_match:
            continue
        records.append((block, {
            'block_id': mutant_id.group(1),
            'program': program_match.group(1),
            'paper': citation.group(1) if citation else (
                contributor.group(1) if contributor else None
            ),
            'schema': 'citation' if citation else (
                'contributor' if contributor else None
            ),
            'equiv': equiv.group(1) if equiv else None,
            'norm_diff': normalize_diff(diff_match.group(1)),
        }))
    return records


def find_removals(records: list[tuple[str, dict]]) -> tuple[list[dict], list[dict], list[tuple]]:
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for _, meta in records:
        by_key[(meta['program'], meta['norm_diff'])].append(meta)

    to_remove: list[dict] = []
    skipped_conflicts: list[tuple] = []
    skipped_other: list[tuple] = []

    for key, group in by_key.items():
        kintis = [r for r in group if r['paper'] == KINTIS]
        if len(kintis) != 2 or {r['schema'] for r in kintis} != {'contributor', 'citation'}:
            continue
        if len({r['equiv'] for r in kintis}) != 1:
            skipped_other.append((key, group, 'kintis label mismatch'))
            continue

        kintis_equiv = kintis[0]['equiv']
        houshmand = [r for r in group if r['paper'] == HOUSHMAND]
        others = [r for r in group if r['paper'] not in (KINTIS, HOUSHMAND)]
        if others:
            skipped_other.append((key, group, 'unexpected extra sources'))
            continue

        if len(houshmand) == 1:
            if houshmand[0]['equiv'] != kintis_equiv:
                skipped_conflicts.append((key, group))
                continue
            to_remove.append([r for r in kintis if r['schema'] == 'contributor'][0])
        elif len(houshmand) == 0 and len(group) == 2:
            to_remove.append([r for r in kintis if r['schema'] == 'contributor'][0])
        else:
            skipped_other.append((key, group, f'houshmand={len(houshmand)} total={len(group)}'))

    return to_remove, skipped_conflicts, skipped_other


def remove_blocks(content: str, block_ids: set[str]) -> str:
    blocks = re.split(r'\n(?=<mb:mutant#)', content)
    kept = []
    for block in blocks:
        mutant_id = re.search(r'<mb:mutant#([^>]+)>', block)
        if mutant_id and mutant_id.group(1) in block_ids:
            continue
        kept.append(block)
    return '\n'.join(kept)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=DATASET)
    parser.add_argument('--apply', action='store_true', help='Write deduplicated dataset.ttl')
    args = parser.parse_args()

    content = args.dataset.read_text()
    records = parse_mutant_blocks(content)
    to_remove, conflicts, skipped = find_removals(records)

    print(f'Mutant blocks parsed: {len(records)}')
    print(f'Redundant contributor records to remove: {len(to_remove)}')
    print(f'Skipped cross-source label conflicts: {len(conflicts)}')
    print(f'Skipped other patterns: {len(skipped)}')

    if args.apply:
        remove_ids = {r['block_id'] for r in to_remove}
        args.dataset.write_text(remove_blocks(content, remove_ids))
        print(f'Wrote deduplicated dataset to {args.dataset}')


if __name__ == '__main__':
    main()
