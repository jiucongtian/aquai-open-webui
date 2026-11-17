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
		expect(splitCompanionBubbles('好呀！我来啦。')).toEqual(['好呀！', '我来啦。']);
	});
	it('caps bubbles without losing the tail', () => {
		expect(splitCompanionBubbles('一\n二\n三\n四\n五\n六')).toEqual([
			'一',
			'二',
			'三',
			'四',
			'五\n六'
		]);
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
