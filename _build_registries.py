# -*- coding: utf-8 -*-
"""
複数バージョンの有効ブロックID一覧を用意する（約5年分）。

- ローカルにある正規(vanilla)の client jar を全部処理
- 足りない過去バージョン(2021-2022)は Mojang 公式から client jar を取得して処理
- 同一のブロック集合は重複排除し、data/blocks_<ver>.txt と data/versions.json を出力

jar 本体は配布せず、抽出した「ブロックIDの一覧（機能的な識別子）」のみを保存する。
"""
import os
import re
import json
import glob
import hashlib
import tempfile
import zipfile
import ssl
import urllib.request
from collections import defaultdict

TOOL = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(TOOL, 'data')
os.makedirs(DATA, exist_ok=True)
APPDATA = os.environ['APPDATA']
MANIFEST = 'https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'

ENSURE = ['1.17.1', '1.18.2', '1.19.4']        # ローカルに無ければ取得して 5 年分にする
VANILLA_RE = re.compile(r'^\d+(\.\d+)+$')        # 1.20.1 / 26.2 のような正規版のみ
_CTX = ssl.create_default_context()


def _open(url, timeout=60):
    return urllib.request.urlopen(url, timeout=timeout, context=_CTX)


def blockset_and_meta(jar_path):
    try:
        with zipfile.ZipFile(jar_path) as z:
            names = z.namelist()
            pre = 'assets/minecraft/blockstates/'
            bs = set(n[len(pre):-5] for n in names if n.startswith(pre) and n.endswith('.json'))
            if not bs:
                return None
            dv = None
            if 'version.json' in names:
                try:
                    vj = json.loads(z.read('version.json'))
                    dv = vj.get('world_version') or vj.get('data_version')
                except Exception:
                    pass
            return bs, dv
    except Exception:
        return None


# ---- ローカル jar を収集 ----
local = {}
for p in glob.glob(os.path.join(APPDATA, 'PrismLauncher', 'libraries', 'com', 'mojang',
                                'minecraft', '*', '*client*.jar')):
    vid = os.path.basename(os.path.dirname(p))
    if VANILLA_RE.match(vid):
        local.setdefault(vid, p)
for d in glob.glob(os.path.join(APPDATA, '.minecraft', 'versions', '*')):
    vid = os.path.basename(d)
    jp = os.path.join(d, vid + '.jar')
    if VANILLA_RE.match(vid) and os.path.isfile(jp):
        local.setdefault(vid, jp)

print('local vanilla jars:', len(local), '->', sorted(local))

# ---- 不足分を Mojang からダウンロード ----
tmp = tempfile.mkdtemp(prefix='mcjars_')
try:
    manifest = json.load(_open(MANIFEST))
    url_by_id = {v['id']: v['url'] for v in manifest['versions']}
except Exception as e:
    url_by_id = {}
    print('manifest fetch failed:', e)

for vid in ENSURE:
    if vid in local:
        continue
    if vid not in url_by_id:
        print('  not in manifest:', vid)
        continue
    try:
        meta = json.load(_open(url_by_id[vid]))
        curl = meta['downloads']['client']['url']
        dest = os.path.join(tmp, vid + '.jar')
        print('  downloading', vid, '...', end=' ', flush=True)
        with _open(curl, timeout=180) as r, open(dest, 'wb') as f:
            f.write(r.read())
        local[vid] = dest
        print('ok (%.1f MB)' % (os.path.getsize(dest) / 1048576))
    except Exception as e:
        print('FAILED', vid, e)

# ---- 全 jar を処理 ----
records = []
for vid, path in local.items():
    r = blockset_and_meta(path)
    if not r:
        continue
    bs, dv = r
    if dv is None:
        continue
    records.append((dv, vid, bs))
records.sort()

# ---- ブロック集合で重複排除（代表= dv 最大）----
groups = defaultdict(list)
for dv, vid, bs in records:
    h = hashlib.md5('\n'.join(sorted(bs)).encode('utf-8')).hexdigest()
    groups[h].append((dv, vid, bs))

registries = []
by_version = {}
for items in groups.values():
    items.sort()
    dv_max, canon, bs = items[-1]
    fname = 'blocks_%s.txt' % canon
    with open(os.path.join(DATA, fname), 'w', encoding='utf-8') as f:
        f.write('\n'.join(sorted(bs)))
    registries.append({'id': canon, 'data_version': dv_max,
                       'file': fname, 'count': len(bs),
                       'members': [v for _, v, _ in items]})
    for dv, vid, _ in items:
        by_version[str(dv)] = fname
registries.sort(key=lambda r: r['data_version'], reverse=True)

# 古い単一ファイルが代表でなければ掃除
keep = set(r['file'] for r in registries)
for old in glob.glob(os.path.join(DATA, 'blocks_*.txt')):
    if os.path.basename(old) not in keep:
        os.remove(old)

with open(os.path.join(DATA, 'versions.json'), 'w', encoding='utf-8') as f:
    json.dump({'registries': registries, 'by_version': by_version},
              f, ensure_ascii=False, indent=1)

print('\nprocessed versions:', len(records), '| unique registries:', len(registries))
for r in registries:
    print('  %-9s dv=%-5s blocks=%-4d  members=%s' %
          (r['id'], r['data_version'], r['count'], r['members']))
