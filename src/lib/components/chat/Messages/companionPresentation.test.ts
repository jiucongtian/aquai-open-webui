import { afterEach, describe, expect, it, vi } from 'vitest';
import {
	companionDelay,
	revealCompanionBubbles,
	splitCompanionBubbles
} from './companionPresentation';

afterEach(() => {
	vi.useRealTimers();
});
describe('companion presentation', () => {
	it('splits mobile-style lines and explicit separators without empty bubbles', () => {
		expect(splitCompanionBubbles('好呀\n\n我来啦|||今天怎么样')).toEqual([
			'好呀',
			'我来啦',
			'今天怎么样'
		]);
	});
	it('preserves a complete thought even when it contains several sentences', () => {
		expect(splitCompanionBubbles('好呀！我来啦。😊')).toEqual(['好呀！我来啦。😊']);
		expect(splitCompanionBubbles('好呀')).toEqual(['好呀']);
	});
	it.each([1, 2, 3, 4, 5])('keeps all %i semantic parts without padding or merging', (count) => {
		const parts = Array.from({ length: count }, (_, index) => `想法${index}。补充说明。`);
		expect(splitCompanionBubbles(parts.join('\n'))).toEqual(parts);
	});
	it('caps display at five bubbles and preserves every overflow paragraph in the last bubble', () => {
		const parts = Array.from({ length: 8 }, (_, index) => `想法${index}。补充说明。`);
		const bubbles = splitCompanionBubbles(parts.join('\n'));
		expect(bubbles).toHaveLength(5);
		expect(bubbles.slice(0, 4)).toEqual(parts.slice(0, 4));
		expect(bubbles[4]).toBe(parts.slice(4).join('\n'));
		expect(bubbles.join('\n')).toBe(parts.join('\n'));
	});
	it('preserves code, tables and numbered instructions', () => {
		for (const content of [
			'```js\na()\nb()\n```',
			'| A | B |\n|---|---|\n|1|2|',
			'1. 第一步\n2. 第二步'
		]) {
			expect(splitCompanionBubbles(content)).toEqual([content]);
		}
	});
	it('uses bounded length-sensitive pauses, with mood affecting pace', () => {
		expect(companionDelay('短', 60, () => 0)).toBe(560);
		expect(companionDelay('长'.repeat(1000), 60, () => 1)).toBe(5850);
		expect(companionDelay('你好', 90, () => 0.5)).toBeLessThan(
			companionDelay('你好', 40, () => 0.5)
		);
	});
	it('reveals one bubble at a time and cancels pending callbacks on disposal', () => {
		vi.useFakeTimers();
		const reveal = vi.fn();
		const dispose = revealCompanionBubbles(['一', '二', '三'], reveal, 60, () => 1000);
		expect(reveal).not.toHaveBeenCalled();
		vi.advanceTimersByTime(1000);
		expect(reveal.mock.calls).toEqual([[1]]);
		vi.advanceTimersByTime(1000);
		expect(reveal.mock.calls).toEqual([[1], [2]]);
		dispose();
		vi.runAllTimers();
		expect(reveal).toHaveBeenCalledTimes(2);
	});
});
