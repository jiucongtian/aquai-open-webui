<script lang="ts">
	import { onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import Modal from '$lib/components/common/Modal.svelte';
	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import { models as availableModels } from '$lib/stores';

	export let chatId = '';
	export let temporary = false;
	export let selection: { enabled: boolean; role_id: string | null } = {
		enabled: false,
		role_id: null
	};
	let roles: any[] = [];
	let show = false;
	let ready = false;
	let busy = false;
	let mounted = false;
	let loadedId: string | null = null;
	let generation = 0;
	let editing = '';
	let name = '';
	let persona = '';
	let modelId = '';
	let interval = 120;
	let dailyMax = 3;
	let awakeFrom = 8;
	let awakeTo = 23;
	let timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Shanghai';
	let confirmAction = '';
	$: selected = roles.find((role) => role.id === selection.role_id);
	$: saved = !!chatId && !/^(local:|temporary:|channel:)/.test(chatId) && !temporary;
	$: if (mounted && loadedId !== chatId) void load(chatId);

	async function api(path = '', method = 'GET', body?: unknown) {
		const response = await fetch(`${WEBUI_API_BASE_URL}/companions${path}`, {
			method,
			headers: {
				Authorization: `Bearer ${localStorage.token}`,
				'Content-Type': 'application/json'
			},
			...(body !== undefined ? { body: JSON.stringify(body) } : {})
		});
		const data = await response.json();
		if (!response.ok)
			throw new Error(typeof data.detail === 'string' ? data.detail : '操作失败，请重试');
		return data;
	}

	async function load(id: string) {
		const ticket = ++generation;
		const previousId = loadedId;
		loadedId = id;
		ready = false;
		try {
			const [items, defaults] = await Promise.all([api('/'), api('/preferences')]);
			if (ticket !== generation) return;
			roles = items;
			if (id && !/^(local:|temporary:|channel:)/.test(id) && !temporary) {
				const current = await api(`/chats/${encodeURIComponent(id)}`);
				if (ticket !== generation) return;
				// A new chat can appear before its first completion initializes the
				// binding. Keep the selection already submitted during that transition.
				if (current.initialized || previousId === null || previousId) selection = current;
			} else {
				selection = defaults;
			}
			if (!roles.some((r) => r.id === selection.role_id))
				selection = { enabled: false, role_id: null };
			ready = true;
		} catch (error) {
			if (ticket === generation) {
				selection = { enabled: false, role_id: null };
				toast.error(String(error));
			}
		}
	}

	async function action(fn: () => Promise<void>) {
		if (busy) return;
		busy = true;
		try {
			await fn();
		} catch (error) {
			toast.error(String(error));
		} finally {
			busy = false;
		}
	}

	async function setSelection(value: typeof selection) {
		await action(async () => {
			if (value.enabled && !value.role_id) {
				show = true;
				return;
			}
			if (saved) await api(`/chats/${encodeURIComponent(chatId)}`, 'PUT', value);
			selection = value;
			roles = await api('/');
		});
	}

	function edit(role: any = null) {
		editing = role?.id || '';
		name = role?.name || '';
		persona = role?.persona || '';
		modelId = role?.model_id || '';
	}

	function openPanel() {
		show = true;
		edit(selected);
		const policy = selected?.state?.proactive || {};
		interval = policy.interval_minutes || 120;
		dailyMax = policy.daily_max || 3;
		awakeFrom = policy.awake_from ?? 8;
		awakeTo = policy.awake_to ?? 23;
		timezone = policy.timezone || timezone;
		void action(async () => {
			roles = await api('/');
		});
	}

	async function saveRole() {
		await action(async () => {
			const body = { name, persona, model_id: modelId };
			const result = await api(editing ? `/${editing}` : '/', editing ? 'PUT' : 'POST', body);
			roles = await api('/');
			if (!editing) {
				const value = { ...selection, role_id: result.id };
				if (saved) await api(`/chats/${encodeURIComponent(chatId)}`, 'PUT', value);
				selection = value;
				editing = result.id;
			}
			toast.success('角色已保存');
		});
	}

	async function proactive(enable: boolean) {
		await action(async () => {
			await api(`/${selected.id}/proactive`, 'PUT', {
				chat_id: enable ? chatId : null,
				interval_minutes: interval,
				daily_max: dailyMax,
				awake_from: awakeFrom,
				awake_to: awakeTo,
				timezone
			});
			roles = await api('/');
			toast.success(enable ? '已设为此角色唯一的主动搭话会话' : '主动搭话已关闭');
		});
	}

	async function confirmed() {
		await action(async () => {
			await api(`/${selected.id}${confirmAction === 'reset' ? '/state' : ''}`, 'DELETE');
			if (confirmAction === 'delete') selection = { enabled: false, role_id: null };
			confirmAction = '';
			roles = await api('/');
			edit(selected);
		});
	}

	onMount(() => {
		mounted = true;
	});
</script>

<div
	class="relative z-10 flex shrink-0 items-center gap-2 px-4 py-1 text-xs text-gray-600 dark:text-gray-300"
>
	<label class="flex items-center gap-2">
		<input
			type="checkbox"
			checked={selection.enabled}
			disabled={!ready || busy}
			on:change={(e) => setSelection({ ...selection, enabled: e.currentTarget.checked })}
		/>
		拟人化模式
	</label>
	<button
		type="button"
		class="rounded px-2 py-1 hover:bg-gray-100 dark:hover:bg-gray-800"
		disabled={!ready || busy}
		on:click={openPanel}
	>
		{selected?.name || '角色与陪伴设置'}
	</button>
	{#if temporary}<span>临时聊天不保存陪伴记忆</span>{/if}
</div>

<Modal bind:show size="lg" ariaLabel="角色与陪伴设置">
	<div class="p-5 space-y-4 max-h-[85vh] overflow-y-auto text-sm">
		<div class="flex justify-between items-center">
			<h2 class="text-lg font-semibold">角色与陪伴设置</h2>
			<button type="button" on:click={() => (show = false)}>关闭</button>
		</div>
		<p class="text-gray-500">
			同一角色跨聊天共享与你的记忆和心情。关闭模式后停止积累，已有数据保留。
		</p>
		<p class="text-gray-500">切换角色或关闭模式会保留本聊天记录；需要完全独立的上下文时，请新建聊天。</p>
		<label class="block"
			>当前角色
			<select
				class="w-full rounded border p-2 bg-transparent"
				value={selection.role_id || ''}
				disabled={busy}
				on:change={(e) => {
					const id = e.currentTarget.value;
					void setSelection({
						...selection,
						role_id: id || null,
						enabled: !!id && selection.enabled
					});
					edit(roles.find((r) => r.id === id));
				}}
			>
				<option value="">请选择角色</option>
				{#each roles as role}<option value={role.id}>{role.name}</option>{/each}
			</select>
		</label>
		<label class="flex items-center gap-2">
			<input
				type="checkbox"
				checked={selection.enabled}
				disabled={busy || !selected}
				on:change={(e) => setSelection({ ...selection, enabled: e.currentTarget.checked })}
			/>
			在此聊天开启拟人化
		</label>
		<button
			type="button"
			class="underline"
			disabled={busy}
			on:click={() =>
				action(async () => {
					await api('/preferences', 'PUT', selection);
					toast.success('仅应用于之后的新聊天');
				})}>将当前开关与角色设为新聊天默认值</button
		>
		<div class="border-t pt-3 space-y-2">
			<div class="flex justify-between">
				<h3 class="font-semibold">{editing ? '编辑角色' : '新增角色'}</h3>
				<button type="button" class="underline" on:click={() => edit()}>新增角色</button>
			</div>
			<label class="block"
				>名称<input
					class="block w-full border rounded p-2 bg-transparent"
					bind:value={name}
					maxlength="80"
				/></label
			>
			<label class="block"
				>人格设定<textarea
					class="block w-full border rounded p-2 bg-transparent"
					rows="5"
					bind:value={persona}
					maxlength="12000"
					placeholder="描述性格、表达习惯、兴趣和相处边界"
				></textarea></label
			>
			<label class="block"
				>主动搭话模型
				<select class="block w-full border rounded p-2 bg-transparent" bind:value={modelId}>
					<option value="">使用最近聊天的模型</option>
					{#each $availableModels as model}<option value={model.id}>{model.name || model.id}</option
						>{/each}
				</select>
			</label>
			<button
				type="button"
				class="rounded bg-gray-900 text-white px-3 py-2 dark:bg-white dark:text-black"
				disabled={busy || !name.trim() || !persona.trim()}
				on:click={saveRole}>保存角色</button
			>
		</div>
		{#if selected}
			<div class="border-t pt-3 space-y-2">
				<h3 class="font-semibold">主动搭话</h3>
				<p class="text-gray-500">
					{selected.target_chat_id === chatId && saved
						? '当前聊天接收主动消息'
						: selected.target_chat_id
							? '此角色已绑定其他聊天；绑定当前聊天会替换原目标'
							: '未开启'}。离线时消息会保存在聊天中。
				</p>
				<div class="grid grid-cols-2 gap-2">
					<label
						>最短间隔（分钟）<input
							class="block w-full border rounded p-2 bg-transparent"
							type="number"
							min="30"
							max="1440"
							bind:value={interval}
						/></label
					>
					<label
						>每日最多生成次数<input
							class="block w-full border rounded p-2 bg-transparent"
							type="number"
							min="1"
							max="10"
							bind:value={dailyMax}
						/></label
					>
					<label
						>开始小时<input
							class="block w-full border rounded p-2 bg-transparent"
							type="number"
							min="0"
							max="23"
							bind:value={awakeFrom}
						/></label
					>
					<label
						>结束小时<input
							class="block w-full border rounded p-2 bg-transparent"
							type="number"
							min="1"
							max="24"
							bind:value={awakeTo}
						/></label
					>
				</div>
				<label class="block"
					>时区<input
						class="block w-full border rounded p-2 bg-transparent"
						bind:value={timezone}
					/></label
				>
				<div class="flex gap-4">
					<button
						type="button"
						class="underline"
						disabled={busy || !saved || !selection.enabled}
						on:click={() => proactive(true)}>开启并绑定当前聊天</button
					><button
						type="button"
						class="underline"
						disabled={busy || !selected.target_chat_id}
						on:click={() => proactive(false)}>关闭主动搭话</button
					>
				</div>
				{#if !saved}<p class="text-gray-500">
						发送第一条消息、保存聊天后即可绑定。临时聊天不可绑定。
					</p>{/if}
			</div>
			<div class="border-t pt-3 space-y-2">
				<h3 class="font-semibold">相处状态与记忆</h3>
				<p>
					心情：{Math.round(
						60 +
							((selected.state.mood ?? 60) - 60) *
								Math.pow(
									0.5,
									Math.max(0, Date.now() / 1000 - (selected.state.mood_at ?? Date.now() / 1000)) /
										21600
								)
					)} / 100
				</p>
				{#if selected.state.profile}<p>{selected.state.profile}</p>{/if}
				{#each selected.state.experience || [] as experience}<p class="text-gray-500">
						{experience}
					</p>{/each}
				{#each selected.state.memories || [] as memory (memory.id)}
					<div class="rounded border p-2 space-y-1">
						<textarea
							aria-label="记忆内容"
							class="w-full bg-transparent"
							bind:value={memory.text}
							maxlength="500"
						></textarea>
						{#if memory.invalid}<span class="text-gray-500">已过时</span>{/if}
						<div class="flex gap-3">
							<button
								type="button"
								class="underline"
								disabled={busy}
								on:click={() =>
									action(async () => {
										await api(`/${selected.id}/memories/${memory.id}`, 'PUT', {
											text: memory.text
										});
										roles = await api('/');
									})}>保存修正</button
							><button
								type="button"
								class="underline"
								disabled={busy}
								on:click={() =>
									action(async () => {
										await api(`/${selected.id}/memories/${memory.id}`, 'DELETE');
										roles = await api('/');
									})}>删除记忆</button
							>
						</div>
					</div>
				{:else}<p class="text-gray-500">还没有长期记忆，开启拟人化聊天后逐渐积累。</p>{/each}
				<div class="flex gap-4 text-red-600">
					<button type="button" disabled={busy} on:click={() => (confirmAction = 'reset')}
						>重置相处状态</button
					><button type="button" disabled={busy} on:click={() => (confirmAction = 'delete')}
						>删除角色</button
					>
				</div>
				{#if confirmAction}<div class="rounded border border-red-300 p-3">
						<p>
							{confirmAction === 'reset'
								? '清空该角色与你的全部陪伴记忆和心情，并关闭主动搭话？'
								: '删除该角色及全部陪伴记忆，并关闭相关聊天的拟人化模式？'}聊天记录保留。
						</p>
						<button type="button" class="mr-4 text-red-600" disabled={busy} on:click={confirmed}
							>确认</button
						><button type="button" on:click={() => (confirmAction = '')}>取消</button>
					</div>{/if}
			</div>
		{/if}
	</div>
</Modal>
