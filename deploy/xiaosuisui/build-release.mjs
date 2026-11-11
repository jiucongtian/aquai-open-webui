// Build from a clean archive of RELEASE_SHA, never the developer's working tree.
import { spawnSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const revision = process.env.RELEASE_SHA;
if (!/^[a-f0-9]{40}$/.test(revision || '')) throw new Error('RELEASE_SHA must be a full Git commit SHA');
const result = spawnSync('npm', ['run', 'build'], {
	stdio: 'inherit',
	env: { ...process.env, APP_BUILD_HASH: revision, APP_BUILD_CHANNEL: 'companion-test' }
});
if (result.status !== 0) process.exit(result.status || 1);
writeFileSync('build/release.json', JSON.stringify({ revision, application: 'xiaosuisui' }) + '\n');
