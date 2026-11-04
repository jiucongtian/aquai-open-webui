"""Apply the matching source identity change to the pinned upstream build."""
from pathlib import Path
import hashlib
import gzip

build = Path('/app/build')
# Match the upstream APP_NAME constant only, not copyright notices or translations.
needle = 'Xo="Open WebUI",lt=""'
chunks = [p for p in (build / '_app/immutable').rglob('*.js') if needle in p.read_text()]
assert len(chunks) == 1, 'Upstream bundle changed; rebuild/review branding patch'
chunk = chunks[0]
updated = chunk.read_text().replace(needle, 'Xo="小岁岁",lt=""')
new_name = 'xiaosuisui-' + hashlib.sha256(updated.encode()).hexdigest()[:12] + '.js'
chunk.with_name(new_name).write_text(updated)
for p in list(build.rglob('*')):
    if not p.is_file() or p.suffix not in ('.js', '.html', '.json', '.css'):
        continue
    text = p.read_text()
    replacement = text.replace(chunk.name, new_name)
    if p.suffix == '.html':
        replacement = replacement.replace('<title>Open WebUI</title>', '<title>小岁岁</title>')
    if replacement != text:
        p.write_text(replacement)
        gz = Path(str(p) + '.gz')
        if gz.exists():
            gz.write_bytes(gzip.compress(replacement.encode()))
        br = Path(str(p) + '.br')
        if br.exists():
            br.unlink()  # Serve the matching uncompressed asset instead.
chunk.write_text(updated)  # Keep old imports valid for browsers with cached entry chunks.
for suffix in ('.gz', '.br'):
    p = Path(str(chunk) + suffix)
    if p.exists():
        p.unlink()
assert '小岁岁' in (build / 'index.html').read_text()
print('Branded title and content-hashed application identity:', new_name)
