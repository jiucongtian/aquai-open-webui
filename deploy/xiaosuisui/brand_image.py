"""Brand the pinned upstream build under one release-specific asset namespace."""
from pathlib import Path
import gzip
import os
import shutil

build = Path('/app/build')
needle = 'Xo="Open WebUI",lt=""'
chunks = [p for p in (build / '_app/immutable').rglob('*.js') if needle in p.read_text()]
assert len(chunks) == 1, 'Upstream bundle changed; rebuild/review branding patch'
chunk = chunks[0]
# Preserve module identity: renaming only one shared store creates duplicate
# state when cached route chunks still import the original module URL.
namespace = '_app-xiaosuisui-' + os.environ['RELEASE_SHA'][:12]
assert namespace != '_app-xiaosuisui-'
for p in list(build.rglob('*')):
    if not p.is_file() or p.suffix not in ('.js', '.html', '.json', '.css'):
        continue
    original = p.read_text()
    updated = original.replace('_app/', namespace + '/')
    updated = updated.replace('"_app"', '"' + namespace + '"').replace("'_app'", "'" + namespace + "'")
    if p == chunk:
        updated = updated.replace(needle, 'Xo="小岁岁",lt=""')
    if p.suffix == '.html':
        updated = updated.replace('<title>Open WebUI</title>', '<title>小岁岁</title>')
    if updated != original:
        p.write_text(updated)
        gz = Path(str(p) + '.gz')
        if gz.exists():
            gz.write_bytes(gzip.compress(updated.encode()))
        br = Path(str(p) + '.br')
        if br.exists():
            br.unlink()
# All module filenames and their relative imports remain unchanged within
# the new namespace; existing tabs retain their old directory until reload.
shutil.copytree(build / '_app', build / namespace)
assert namespace in (build / 'index.html').read_text()
assert '小岁岁' in (build / 'index.html').read_text()
print('Branded build namespace:', namespace)
