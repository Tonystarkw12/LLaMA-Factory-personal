#!/usr/bin/env python3
"""Read-only structural and split audit for GRPO artifacts."""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

ROOT = Path('/mnt/d1/tony/outputs/grpo_data')
FILES = sorted(ROOT.glob('*.jsonl'))


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def text_hash(value: str) -> str:
    return sha_bytes(value.encode())


def load(path: Path):
    rows = []
    errors = []
    with path.open() as handle:
        for line_no, line in enumerate(handle, 1):
            try:
                row = json.loads(line)
                rows.append(row)
            except Exception as exc:
                errors.append(dict(line=line_no, error=type(exc).__name__, message=str(exc)))
    return rows, errors


def fp(row: dict) -> dict[str, str]:
    output = row.get('output', row.get('chosen', ''))
    instruction = row.get('instruction', '')
    inp = row.get('input', '')
    return dict(id=str(row.get('id', '')), output=text_hash(output), prompt=text_hash(instruction + '\n' + inp),
                input=text_hash(inp), task=str(row.get('task_name', '')), family=str(row.get('family', '')))


def main():
    result = dict(root=str(ROOT), files={}, cross_checks={}, source_hashes={})
    sets = {}
    for path in FILES:
        raw = path.read_bytes()
        rows, errors = load(path)
        sets[path.name] = rows
        key_counts = collections.Counter(tuple(sorted(r.keys())) for r in rows)
        fprints = [fp(r) for r in rows]
        duplicate = {}
        for kind in ('id', 'output', 'prompt', 'input'):
            c = collections.Counter(x[kind] for x in fprints if x[kind])
            duplicate[kind] = dict(unique=len(c), repeated_rows=sum(n - 1 for n in c.values() if n > 1),
                                    max_multiplicity=max(c.values(), default=0))
        missing = []
        for n, r in enumerate(rows, 1):
            # Alpaca input is optional; an empty input is not a defective sample.
            required = ('instruction', 'output') if 'output' in r else ('instruction', 'chosen', 'rejected') if 'chosen' in r else ()
            for key in required:
                if not isinstance(r.get(key), str) or not r[key].strip():
                    missing.append(dict(line=n, field=key))
        result['files'][path.name] = dict(rows=len(rows), bytes=len(raw), sha256=sha_bytes(raw),
            parse_errors=errors, key_shapes={str(k): v for k,v in key_counts.items()},
            duplicate_fingerprints=duplicate, missing_required=missing[:100], missing_count=len(missing),
            families=dict(collections.Counter(r.get('family') for r in rows)),
            task_names=dict(collections.Counter(r.get('task_name') for r in rows)),
            static_parse_status=dict(collections.Counter((json.loads(r['static']).get('parse_status') if isinstance(r.get('static'), str) and r['static'].startswith('{') else 'absent') for r in rows)),
            empty_optional_input=sum(not r.get('input', '').strip() for r in rows),
            reference_fields=dict((k, sum(k in r and bool(r[k]) for r in rows)) for k in ('ref_sleepy','ref_prodopy','static','task_name','family')))
        result['source_hashes'][path.name] = result['files'][path.name]['sha256']
    # Exact and program-level overlaps among the principal partitions.
    principal = ['grpo_train.jsonl', 'grpo_val.jsonl', 'gate10_singles_test.jsonl', 'gate10_doubles_test.jsonl', 'gate11_singles_train.jsonl', 'rm_run3_train.jsonl']
    for a in principal:
        if a not in sets: continue
        af = [fp(r) for r in sets[a]]
        for b in principal:
            if b <= a or b not in sets: continue
            bf = [fp(r) for r in sets[b]]
            details = {}
            for kind in ('id','output','prompt','input'):
                av = {x[kind] for x in af if x[kind]}
                hits = [i+1 for i,x in enumerate(bf) if x[kind] in av]
                details[kind] = dict(rows=len(hits), lines=hits[:100])
            result['cross_checks'][f'{a} vs {b}'] = details
    (ROOT / 'grpo_audit_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
