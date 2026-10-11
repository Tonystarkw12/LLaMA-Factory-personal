"""Execute scorer pure functions without loading simulation services."""
import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path('/mnt/d1/tony/outputs')
PATHS = [ROOT/'nmr_rl/scripts/nmr_reward_server.py', ROOT/'nmr_rl_v3/nmr_reward_server.py']


def functions(path):
    tree = ast.parse(path.read_text())
    wanted = {'normalize_dimension', 'declared_dimension', 'static_score', 'static_fingerprint'}
    funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    env = {'re': re, 'parse_string': lambda *a, **kw: None,
           'timeline_sim': lambda *a: None, 'timeline_tokens': lambda *a: None}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(path), 'exec'), env)
    return env


@pytest.mark.parametrize('path', PATHS)
@pytest.mark.parametrize('declaration,label', [('3D', '3D'), ('7D', '7D'), ('pseudo 2D', 'pseudo-2D'), ('1D and 2D', '1D/2D')])
def test_identical_declared_dimensions_get_full_static_credit(path, declaration, label):
    assert functions(path)['static_score'](f';$DIM={declaration}\n1 ze\n', {'dim': label}) == pytest.approx(1.0)


@pytest.mark.parametrize('path', PATHS)
def test_unknown_does_not_become_1d_and_known_mismatch_is_penalized(path):
    funcs = functions(path)
    assert funcs['declared_dimension'](';comparison to a 1D reference\n1 ze\n') is None
    assert funcs['static_score']('1 ze\n', {'dim': '1D'}) == pytest.approx(0.85)
    assert funcs['static_score'](';$DIM=3D\n1 ze\n', {'dim': None}) == pytest.approx(1.0)
    assert funcs['declared_dimension'](';$DIM=1D\n;$DIM=2D\n') is None


def test_builder_dimension_matches_all_existing_repaired_gold():
    funcs = functions(ROOT/'nmr_rl/scripts/build_grpo_dataset.py')
    for split in ('train', 'validation', 'test'):
        for line in (ROOT/'grpo_data/clean_v3'/f'{split}.jsonl').open():
            row = json.loads(line)
            assert funcs['static_fingerprint'](row['output'])['dim'] == json.loads(row['static'])['dim'], row['id']
