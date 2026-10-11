#!/usr/bin/env python3
"""Build a source-preserving, program-group-disjoint GRPO split.

The existing GRPO files are read-only inputs. The output directory is created
with exclusive semantics so this script cannot silently replace a prior build.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ROOT = Path('/mnt/d1/tony/outputs/grpo_data')
OUT = ROOT / 'clean_v1'
QUARANTINE = REPO / 'data/nmr_v3/quality_audit_20260923/quarantine_final.jsonl'
SEED = 42
INPUTS = ('grpo_train.jsonl', 'grpo_val.jsonl')


def digest(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


def read(path: Path) -> tuple[list[dict], list[bytes]]:
    raw_lines = path.read_bytes().splitlines(keepends=True)
    return [json.loads(line) for line in raw_lines], raw_lines


def output_fingerprints(output: str) -> dict[str, str]:
    output = output.strip()
    body = '\n'.join(line.strip() for line in output.splitlines()
                      if line.strip() and not line.lstrip().startswith(';'))
    first = output.splitlines()[0].lstrip(';').strip() if output else ''
    name = first.lower() if output.startswith(';') and re.fullmatch(r'[A-Za-z][\w.-]*', first) else ''
    family = re.sub(r'(?:\.\d+)+$', '', name)
    return dict(output=digest(output), body=digest(body), name=name,
                name_numeric_family=family)


def fingerprints(row: dict) -> dict[str, str]:
    fp = output_fingerprints(row['output'])
    fp['prompt'] = digest('\n'.join((row.get('instruction', ''), row.get('input', ''))))
    return fp


def union_groups(rows: list[dict]) -> tuple[list[str], list[str]]:
    parent = list(range(len(rows)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    seen: dict[tuple[str, str], int] = {}
    all_fp = [fingerprints(row) for row in rows]
    for index, fp in enumerate(all_fp):
        for kind, value in fp.items():
            if not value:
                continue
            key = (kind, value)
            if key in seen:
                parent[find(index)] = find(seen[key])
            seen[key] = index
    members: dict[int, list[int]] = collections.defaultdict(list)
    for index in range(len(rows)):
        members[find(index)].append(index)
    group_id_by_root = {
        root: digest('\n'.join(sorted(all_fp[index]['output'] for index in indexes)))
        for root, indexes in members.items()
    }
    ordered = sorted(group_id_by_root.values(), key=lambda group: digest(f'{SEED}:{group}'))
    heldout = max(1, round(len(ordered) * 0.05))
    assignment = {
        group: ('test' if position < heldout else 'validation' if position < 2 * heldout else 'train')
        for position, group in enumerate(ordered)
    }
    splits = [assignment[group_id_by_root[find(index)]] for index in range(len(rows))]
    groups = [group_id_by_root[find(index)] for index in range(len(rows))]
    return splits, groups


def json_field_counts(rows: list[dict]) -> dict:
    counts = collections.Counter()
    malformed = collections.Counter()
    for row in rows:
        counts['engine_support_false' if not row.get('engine_support') else 'engine_support_true'] += 1
        counts['ref_sleepy_present' if row.get('ref_sleepy') else 'ref_sleepy_empty'] += 1
        counts['ref_prodopy_present' if row.get('ref_prodopy') else 'ref_prodopy_empty'] += 1
        for field in ('static', 'ref_sleepy', 'ref_prodopy', 'ref_timeline', 'db_meta'):
            if not row.get(field):
                continue
            try:
                json.loads(row[field])
            except (TypeError, ValueError):
                malformed[field] += 1
    return dict(counts=counts, malformed_json=malformed)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f'refusing to overwrite {OUT}')
    OUT.mkdir(parents=True)
    rows: list[dict] = []
    source_lines: list[bytes] = []
    source_refs: list[dict] = []
    source_hashes = {}
    for filename in INPUTS:
        path = ROOT / filename
        source_raw = path.read_bytes()
        source_hashes[filename] = digest(source_raw)
        source_rows, lines = read(path)
        start = len(rows)
        rows.extend(source_rows)
        source_lines.extend(lines)
        source_refs.extend(dict(source_file=filename, source_line=index + 1)
                           for index in range(len(source_rows)))
        assert len(rows) - start == len(lines)

    quarantine = {(
        item['record']['instruction'], item['record']['input'], item['record']['output']
    ): item for item in map(json.loads, QUARANTINE.read_text().splitlines())}
    excluded = [index for index, row in enumerate(rows)
                if (row.get('instruction'), row.get('input'), row.get('output')) in quarantine]
    assert len(excluded) == 253, len(excluded)
    excluded_set = set(excluded)
    kept_indexes = [index for index in range(len(rows)) if index not in excluded_set]
    kept_rows = [rows[index] for index in kept_indexes]
    splits, groups = union_groups(kept_rows)

    output_files = {}
    for split in ('train', 'validation', 'test'):
        indexes = [position for position, value in enumerate(splits) if value == split]
        payload = b''.join(source_lines[kept_indexes[position]] for position in indexes)
        path = OUT / f'{split}.jsonl'
        path.write_bytes(payload)
        output_files[split] = dict(file=path.name, rows=len(indexes), sha256=digest(payload),
                                   groups=len({groups[position] for position in indexes}),
                                   reference_fields=json_field_counts([kept_rows[position] for position in indexes]))

    with (OUT / 'row_manifest.jsonl').open('x') as handle:
        for position, original_index in enumerate(kept_indexes):
            row = kept_rows[position]
            handle.write(json.dumps(dict(
                clean_line=position + 1, source=source_refs[original_index], id=row['id'],
                split=splits[position], group_id=groups[position], fingerprints=fingerprints(row),
                engine_support=row.get('engine_support'), ref_sleepy=bool(row.get('ref_sleepy')),
                ref_prodopy=bool(row.get('ref_prodopy'))), ensure_ascii=False) + '\n')
    with (OUT / 'excluded_quarantine.jsonl').open('x') as handle:
        for index in excluded:
            handle.write(json.dumps(dict(source=source_refs[index], id=rows[index]['id'],
                                         quarantine=quarantine[(rows[index]['instruction'], rows[index]['input'], rows[index]['output'])]),
                                     ensure_ascii=False) + '\n')

    overlap = {}
    for left in ('train', 'validation', 'test'):
        left_pos = [position for position, value in enumerate(splits) if value == left]
        left_fp = [fingerprints(kept_rows[position]) for position in left_pos]
        overlap[left] = {}
        for right in ('train', 'validation', 'test'):
            if right <= left:
                continue
            right_pos = [position for position, value in enumerate(splits) if value == right]
            right_fp = [fingerprints(kept_rows[position]) for position in right_pos]
            overlap[left + '_vs_' + right] = {
                kind: len({x[kind] for x in left_fp if x[kind]} & {x[kind] for x in right_fp if x[kind]})
                for kind in ('output', 'body', 'name', 'name_numeric_family', 'prompt')
            }

    manifest = dict(version='grpo_clean_v1', seed=SEED, source_files=source_hashes,
                    source_rows=len(rows), excluded_rows=len(excluded), kept_rows=len(kept_rows),
                    exclusion_reason='exact instruction/input/output match to SFT quarantine_final.jsonl',
                    files=output_files, overlap=overlap,
                    group_method='transitive union of exact output, comment-stripped body, first-line name, numeric name family, prompt',
                    limitation='Static and reference fields are preserved; no TopSpin compile or new reward execution was run.')
    write_json(OUT / 'manifest.json', manifest)
    write_json(OUT / 'build_stats.json', dict(train=output_files['train']['rows'],
                                               validation=output_files['validation']['rows'],
                                               test=output_files['test']['rows'],
                                               groups=sum(v['groups'] for k, v in output_files.items()),
                                               excluded=len(excluded),
                                               source_rows=len(rows),
                                               engine_support_false=sum(not row.get('engine_support') for row in kept_rows),
                                               ref_sleepy_empty=sum(not row.get('ref_sleepy') for row in kept_rows),
                                               ref_prodopy_empty=sum(not row.get('ref_prodopy') for row in kept_rows)))
    write_json(OUT / 'verification.json', dict(status='PASS', source_hashes=source_hashes,
        source_files_unchanged=all(digest((ROOT / filename).read_bytes()) == value
                                   for filename, value in source_hashes.items()),
        source_rows=len(rows), excluded_rows=len(excluded), kept_rows=len(kept_rows),
        output_rows=sum(v['rows'] for v in output_files.values()), overlap=overlap,
        excluded_exactly_quarantine=len(excluded) == 253))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
