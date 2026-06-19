"""Audit and optionally remove redundant Kintis mutant records in dataset.ttl.

Duplicate detection groups records by program, identical -/+ patch lines, and
source line numbers within +/-1 (Kintis re-imports often differ by one line in
the diff hunk header). Within such a cluster, a schema:contributor Kintis record
is redundant when a schema:citation Kintis record exists with the same label.

Cross-source label conflicts (e.g. Kintis EQ vs Houshmand NEQ) are reported but
do not block deduplication of the redundant Kintis contributor copy.
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

DATASET = Path(__file__).resolve().parent / 'dataset.ttl'
KINTIS = 'kintis2016analysing'
HOUSHMAND = 'houshmand2017tce'
LINE_TOLERANCE = 1


def patch_lines(diff: str) -> str:
    lines = [
        line for line in diff.strip().split('\n')
        if line.startswith('-') or line.startswith('+')
    ]
    return '\n'.join(sorted(lines))


def parse_old_line(diff: str) -> int | None:
    match = re.search(r'@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@', diff)
    return int(match.group(1)) if match else None


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
        diff = diff_match.group(1)
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
            'patch_lines': patch_lines(diff),
            'old_line': parse_old_line(diff),
        }))
    return records


def cluster_by_line(records: list[dict]) -> list[list[dict]]:
    """Group records whose old_line values are within LINE_TOLERANCE."""
    size = len(records)
    parent = list(range(size))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for i in range(size):
        line_i = records[i]['old_line']
        if line_i is None:
            continue
        for j in range(i + 1, size):
            line_j = records[j]['old_line']
            if line_j is not None and abs(line_i - line_j) <= LINE_TOLERANCE:
                union(i, j)

    clusters: dict[int, list[dict]] = defaultdict(list)
    for index, record in enumerate(records):
        clusters[find(index)].append(record)
    return list(clusters.values())


def find_removals(records: list[tuple[str, dict]]) -> tuple[list[dict], list[tuple], list[tuple]]:
    by_patch: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for _, meta in records:
        by_patch[(meta['program'], meta['patch_lines'])].append(meta)

    to_remove: list[dict] = []
    reported_conflicts: list[tuple] = []
    skipped_other: list[tuple] = []

    for patch_key, bucket in by_patch.items():
        for cluster in cluster_by_line(bucket):
            if len(cluster) < 2:
                continue

            kintis = [r for r in cluster if r['paper'] == KINTIS]
            if len(kintis) != 2 or {r['schema'] for r in kintis} != {'contributor', 'citation'}:
                continue
            if len({r['equiv'] for r in kintis}) != 1:
                skipped_other.append((patch_key, cluster, 'kintis label mismatch'))
                continue

            kintis_equiv = kintis[0]['equiv']
            houshmand = [r for r in cluster if r['paper'] == HOUSHMAND]
            others = [r for r in cluster if r['paper'] not in (KINTIS, HOUSHMAND)]
            if others:
                skipped_other.append((patch_key, cluster, 'unexpected extra sources'))
                continue

            cluster_key = (patch_key, tuple(sorted(r['block_id'] for r in cluster)))
            if len(houshmand) == 1:
                if houshmand[0]['equiv'] != kintis_equiv:
                    reported_conflicts.append((cluster_key, cluster))
                to_remove.append([r for r in kintis if r['schema'] == 'contributor'][0])
            elif len(houshmand) == 0 and len(cluster) == 2:
                to_remove.append([r for r in kintis if r['schema'] == 'contributor'][0])
            else:
                skipped_other.append((
                    patch_key, cluster, f'houshmand={len(houshmand)} total={len(cluster)}'
                ))

    return to_remove, reported_conflicts, skipped_other


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

    by_program: dict[str, int] = defaultdict(int)
    for record in to_remove:
        by_program[record['program']] += 1

    print(f'Mutant blocks parsed: {len(records)}')
    print(f'Line tolerance: +/-{LINE_TOLERANCE}')
    print(f'Redundant contributor records to remove: {len(to_remove)}')
    print(f'Reported cross-source label conflicts: {len(conflicts)}')
    print(f'Skipped other patterns: {len(skipped)}')
    if by_program:
        print('Affected programs:')
        for program, count in sorted(by_program.items()):
            print(f'  {program}: {count}')

    if args.apply:
        remove_ids = {r['block_id'] for r in to_remove}
        args.dataset.write_text(remove_blocks(content, remove_ids))
        print(f'Wrote deduplicated dataset to {args.dataset}')


if __name__ == '__main__':
    main()
