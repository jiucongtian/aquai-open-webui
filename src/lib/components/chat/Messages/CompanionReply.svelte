<script lang="ts">
	import { onMount, onDestroy, tick } from 'svelte';
	import {
		liveCompanionReplies,
		splitCompanionBubbles,
		revealCompanionBubbles
	} from './companionPresentation';

	export let content = '';
	export let done = false;
	export let cancelled = false;
	export let replyKey = '';
	export let name = '对方';
	export let mood = 60;
	let element: HTMLDivElement;
	let mounted = false;
	let animate = false;
	let started = false;
	let visible = 0;
	let cancel: (() => void) | undefined;
	let reducedMotion = false;
	let displayedContent = '';
	$: parts = splitCompanionBubbles(content);
	$: typing = !cancelled && (!done || visible < parts.length);
	$: if (mounted) reconcile(done, cancelled, parts);

	function reconcile(finished: boolean, stopped: boolean, bubbles: string[]) {
		if (stopped || reducedMotion || !animate) {
			cancel?.();
			visible = finished || stopped ? bubbles.length : 0;
			return;
		}
		if (finished && started && displayedContent !== content) {
			cancel?.();
			animate = false;
			visible = bubbles.length;
			return;
		}
		if (!finished || started) return;
		started = true;
		displayedContent = content;
		cancel = revealCompanionBubbles(
			bubbles,
			(count) => {
				reveal(count);
			},
			mood
		);
	}

	async function reveal(count: number) {
		const container = element?.closest('[id^="messages-container"]');
		const follow =
			container && container.scrollHeight - container.scrollTop - container.clientHeight < 80;
		visible = count;
		await tick();
		if (follow && container) container.scrollTop = container.scrollHeight;
	}

	function showAll() {
		cancel?.();
		animate = false;
		void reveal(parts.length);
	}

	onMount(() => {
		animate = liveCompanionReplies.delete(replyKey) || !done;
		reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
		mounted = true;
	});
	onDestroy(() => cancel?.());
</script>

<div bind:this={element} class="flex flex-col items-start gap-2 py-1" data-testid="companion-reply">
	{#each parts.slice(0, visible) as bubble, index (index)}
		<div
			class="max-w-full rounded-2xl rounded-tl-sm bg-gray-100 px-4 py-2.5 text-gray-900 dark:bg-gray-850 dark:text-gray-100 whitespace-pre-wrap break-words"
			data-testid="companion-bubble"
		>
			{bubble}
		</div>
	{/each}
	{#if typing}
		<div
			role="status"
			aria-live="polite"
			class="flex items-center gap-2 px-2 py-1 text-xs text-gray-500"
			data-testid="companion-typing"
		>
			<span class="tracking-widest motion-safe:animate-pulse" aria-hidden="true">•••</span>
			<span>{name}正在输入…</span>
		</div>
	{/if}
	{#if done && typing}
		<button type="button" class="px-2 text-xs text-gray-500 hover:underline" on:click={showAll}
			>显示全部</button
		>
	{/if}
</div>
