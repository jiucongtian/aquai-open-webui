/** Presentation only: never split a conversation turn or modify its stored answer. */
export const liveCompanionReplies = new Set<string>();
export const MAX_COMPANION_BUBBLES = 5;

export function splitCompanionBubbles(text: string): string[] {
	const value = text.trim();
	if (!value) return [];
	// Preserve structured answers rather than breaking Markdown semantics.
	if (/```|~~~|^\s*(?:#{1,6}\s|[-*+]\s|\d+[.)、]\s|>\s|\|)|<\/?[a-z]/im.test(value)) {
		return [value];
	}
	// The model chooses semantic boundaries. Do not force a sentence count,
	// split punctuation, or pad the reply to reach the safety ceiling.
	const parts = value
		.split(/\|\|\||\n+/)
		.map((part) => part.trim())
		.filter(Boolean);
	// Limit notifications/pauses without discarding any of the reply.
	return parts.length > MAX_COMPANION_BUBBLES
		? [
				...parts.slice(0, MAX_COMPANION_BUBBLES - 1),
				parts.slice(MAX_COMPANION_BUBBLES - 1).join('\n')
			]
		: parts;
}

export function companionDelay(text: string, mood = 60, random = Math.random): number {
	const speed = mood >= 85 ? 0.85 : mood < 50 ? 1.15 : 1;
	return Math.round(
		Math.min(4500, Math.max(700, 350 + [...text].length * 110)) * (0.8 + random() * 0.5) * speed
	);
}

/** One cancellable timer at a time; dispose/skip never leave delayed callbacks behind. */
export function revealCompanionBubbles(
	parts: string[],
	onReveal: (count: number) => void,
	mood = 60,
	delay = companionDelay
) {
	let timer: ReturnType<typeof setTimeout> | undefined;
	let disposed = false;
	let count = 0;
	const next = () => {
		if (disposed || count >= parts.length) return;
		timer = setTimeout(
			() => {
				if (disposed) return;
				onReveal(++count);
				next();
			},
			delay(parts[count], mood)
		);
	};
	next();
	return () => {
		disposed = true;
		clearTimeout(timer);
	};
}
