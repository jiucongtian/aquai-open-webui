import { WEBUI_API_BASE_URL } from '$lib/constants';

/** Save the temporary chat's explicit choice before navigating to its saved id. */
export async function persistCompanionSelection(
	token: string,
	chatId: string,
	selection: { enabled: boolean; role_id: string | null }
) {
	const response = await fetch(
		`${WEBUI_API_BASE_URL}/companions/chats/${encodeURIComponent(chatId)}`,
		{
			method: 'PUT',
			headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
			body: JSON.stringify(selection)
		}
	);
	if (!response.ok) throw new Error('聊天已保存，但拟人化设置保存失败，请重试');
}
