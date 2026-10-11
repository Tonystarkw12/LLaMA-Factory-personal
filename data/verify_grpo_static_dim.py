#!/usr/bin/env python3
"""Verify GRPO clean_v2 static.dim repair against clean_v1 evidence."""
import collections
import hashlib
import json
import re
from pathlib import Path

ROOT=Path('/mnt/d1/tony/outputs/grpo_data')
V1=ROOT/'clean_v1'
V2=ROOT/'clean_v2'
SPLITS=('train','validation','test')


def sha(data): return hashlib.sha256(data).hexdigest()


def normalize(raw):
    value=re.sub(r'\s+',' ',raw.strip()).upper()
    if re.fullmatch(r'[1-9][0-9]*D',value):return value
    pseudo=re.fullmatch(r'PSEUDO[ _-]+([1-9][0-9]*D)',value)
    if pseudo:return 'pseudo-'+pseudo.group(1)
    if re.fullmatch(r'[1-9][0-9]*D(?:\s*(?:,|AND|/)\s*[1-9][0-9]*D)+',value):
        return '/'.join(dict.fromkeys(re.findall(r'[1-9][0-9]*D',value)))
    return None


def main():
    changes=[];counts=collections.Counter()
    for split in SPLITS:
        before=(V1/f'{split}.jsonl').read_bytes().splitlines()
        after=(V2/f'{split}.jsonl').read_bytes().splitlines()
        assert len(before)==len(after)
        for line_no,(a,b) in enumerate(zip(before,after),1):
            old=json.loads(a);new=json.loads(b)
            old_static=json.loads(old.pop('static'));new_static=json.loads(new.pop('static'))
            assert old==new, (split,line_no,'non-static field changed')
            assert {k:v for k,v in old_static.items() if k!='dim'}=={k:v for k,v in new_static.items() if k!='dim'}
            headers=re.findall(r'^[ \t]*;[ \t]*\$DIM[ \t]*=([^\r\n]*)',new['output'],re.M|re.I)
            values=[normalize(h) for h in headers]
            unique=set(values)
            if not headers or not any(h.strip() for h in headers): expected=None;state='missing_header'
            elif None in unique:expected=None;state='unknown_header'
            elif len(unique)>1:expected=None;state='conflicting_headers'
            else:expected=values[0];state='header_derived'
            actual=new_static
            assert actual['dim']==expected,(split,line_no,expected,actual['dim'],headers)
            counts[(state,str(expected))]+=1
            if old_static.get('dim')!=expected or state!='header_derived':
                changes.append((split,line_no,old_static.get('dim'),expected,state,[] if state=='missing_header' else headers))
    repair_rows=[json.loads(x) for x in (V2/'static_dim_repairs.jsonl').read_text().splitlines()]
    assert len(repair_rows)==len(changes)
    for actual,expected in zip(repair_rows,changes):
        assert (actual['split'],actual['line'],actual['old_static_dim'],actual['new_static_dim'],actual['status'],actual['header_values'])==expected
    manifest=json.loads((V2/'manifest.json').read_text())
    source_manifest=json.loads((V1/'manifest.json').read_text())
    assert manifest['parent_source_manifest_sha256']==sha((V1/'manifest.json').read_bytes())
    for split in SPLITS:
        assert manifest['parent_files'][split]==source_manifest['files'][split]['sha256']
        assert manifest['parent_files'][split]==sha((V1/f'{split}.jsonl').read_bytes())
        assert manifest['files'][split]['sha256']==sha((V2/f'{split}.jsonl').read_bytes())
    receipt=dict(status='PASS',only_static_dim_changed=True,rows=sum(sum(1 for _ in (V2/f'{s}.jsonl').open()) for s in SPLITS),
                 counts={f'{k}:{d}':n for (k,d),n in counts.items()},repair_receipts=len(repair_rows),
                 parent_sha256={s:sha((V1/f'{s}.jsonl').read_bytes()) for s in SPLITS},
                 output_sha256={s:sha((V2/f'{s}.jsonl').read_bytes()) for s in SPLITS})
    (V2/'static_dim_verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
