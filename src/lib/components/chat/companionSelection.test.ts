import { afterEach, expect, it, vi } from 'vitest';
vi.mock('$lib/constants', () => ({ WEBUI_API_BASE_URL: '/api/v1' }));
import { persistCompanionSelection } from './companionSelection';

afterEach(() => vi.unstubAllGlobals());

it.each([true, false])('persists the explicit saved-chat choice, enabled=%s', async (enabled) => {
	const fetch = vi.fn().mockResolvedValue({ ok: true });
	vi.stubGlobal('fetch', fetch);
	await persistCompanionSelection('test-token', 'saved-chat', { enabled, role_id: 'role' });
	expect(fetch).toHaveBeenCalledWith('/api/v1/companions/chats/saved-chat', {
		method: 'PUT',
		headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' },
		body: JSON.stringify({ enabled, role_id: 'role' })
	});
});

it('rejects failed persistence instead of reporting the save as successful', async () => {
	vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
	await expect(
		persistCompanionSelection('test-token', 'saved-chat', {
			enabled: true,
			role_id: 'role'
		})
	).rejects.toThrow('拟人化设置保存失败');
});
