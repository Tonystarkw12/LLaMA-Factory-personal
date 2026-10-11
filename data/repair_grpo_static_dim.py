#!/usr/bin/env python3
"""Repair GRPO static.dim from the pulse program's explicit $DIM header.

Creates clean_v2 from clean_v1 without changing any other value. The raw
GRPO inputs and clean_v1 remain untouched. Missing/unknown/conflicting
headers are represented as null rather than guessed.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
from pathlib import Path

ROOT = Path('/mnt/d1/tony/outputs/grpo_data')
SOURCE = ROOT/'clean_v1'
OUT = ROOT/'clean_v2'
SPLITS = ('train','validation','test')


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_dim(raw: str) -> str | None:
    value = re.sub(r'\s+', ' ', raw.strip()).upper()
    if re.fullmatch(r'[1-9][0-9]*D', value):
        return value
    pseudo = re.fullmatch(r'PSEUDO[ _-]+([1-9][0-9]*D)', value)
    if pseudo:
        return 'pseudo-' + pseudo.group(1)
    if re.fullmatch(r'[1-9][0-9]*D(?:\s*(?:,|AND|/)\s*[1-9][0-9]*D)+', value):
        return '/'.join(dict.fromkeys(re.findall(r'[1-9][0-9]*D', value)))
    return None


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f'refusing to overwrite {OUT}')
    OUT.mkdir()
    src_manifest=json.loads((SOURCE/'manifest.json').read_text())
    result={}
    repairs=[]
    dim_counts=collections.Counter()
    for split in SPLITS:
        source_lines=(SOURCE/f'{split}.jsonl').read_bytes().splitlines(keepends=True)
        target_lines=[]
        for line_no,raw_line in enumerate(source_lines,1):
            row=json.loads(raw_line)
            static=json.loads(row['static'])
            old=static.get('dim')
            headers=re.findall(r'^[ \t]*;[ \t]*\$DIM[ \t]*=([^\r\n]*)',row['output'],re.M|re.I)
            normalized=[normalize_dim(value) for value in headers]
            unique=set(normalized)
            if not headers or not any(h.strip() for h in headers):
                new=None; status='missing_header'; raw_value=[]
            elif None in unique:
                new=None; status='unknown_header'; raw_value=headers
            elif len(unique)>1:
                new=None; status='conflicting_headers'; raw_value=headers
            else:
                new=normalized[0]; status='header_derived'; raw_value=headers
            static['dim']=new
            row['static']=json.dumps(static,ensure_ascii=False,separators=(',',':'))
            encoded=json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()+b'\n'
            target_lines.append(encoded)
            dim_counts[(status,str(new))]+=1
            if old!=new or status!='header_derived':
                repairs.append(dict(split=split,line=line_no,id=row['id'],old_static_dim=old,
                                    new_static_dim=new,header_values=raw_value,status=status,
                                    evidence='explicit ;$DIM header; static.dim is derived metadata'))
        payload=b''.join(target_lines)
        (OUT/f'{split}.jsonl').write_bytes(payload)
        result[split]=dict(file=f'{split}.jsonl',rows=len(target_lines),sha256=sha(payload),
                           groups=src_manifest['files'][split]['groups'])
        assert len(source_lines)==len(target_lines)
    with (OUT/'static_dim_repairs.jsonl').open('x') as handle:
        for repair in repairs:
            handle.write(json.dumps(repair,ensure_ascii=False)+'\n')
    for filename in ('row_manifest.jsonl','excluded_quarantine.jsonl',
                     'cross_stage_exposure.json','build_stats.json'):
        path=SOURCE/filename
        if path.exists():
            (OUT/filename).write_bytes(path.read_bytes())
    manifest=dict(version='grpo_clean_v2',parent='clean_v1',
        parent_source_manifest_sha256=sha((SOURCE/'manifest.json').read_bytes()),
        builder_sha256=sha(Path(__file__).read_bytes()),
        parent_files={split:sha((SOURCE/f'{split}.jsonl').read_bytes()) for split in SPLITS},
        files=result,rows=sum(v['rows'] for v in result.values()),
        repair='Only static.dim changed. It is set from a recognized explicit ;$DIM header; missing, unknown, or conflicting declarations become null.',
        statuses={f'{status}:{dim}':n for (status,dim),n in dim_counts.items()},
        limitations='Declared TopSpin dimension is copied as metadata, not validated against execution or spectroscopy. Other static fields remain unchanged.')
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
