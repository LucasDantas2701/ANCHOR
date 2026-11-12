import { Component, computed, input, signal } from '@angular/core';

import { Copy, TESTS_URL } from './copy';

/**
 * The measured numbers behind each question, for an ordinary robot (a fixed-selector script), an AI in
 * control and ANCHOR, in that order. They are kept here, apart from the words, so both languages always
 * show the same ones. From the repository's result files (development sets, version 0.5; the 9B model
 * where a model is used); update them from the final run's.
 *   1. the resilience benchmark, tasks done of 150 runs each: 53%, 73%, 96%
 *      (resilience_20261016-183128_74657b0 and resilience_20261102-222400_9694f30);
 *   2. the same runs, false successes (said done when it was not): 0, 40, 0;
 *   3. the injection suite, runs in which an attack worked, of 24 (both models): the AI in control 3
 *      (plans_20261108-220131_cfa6c56_injection_llm), ANCHOR 0 (plans_20261102..._9694f30_injection);
 *      the script does not read the page, so it has no number here.
 */
const NUMBERS: { values: (number | null)[]; scale: number; lessIsBetter: boolean }[] = [
  { values: [53, 73, 96], scale: 100, lessIsBetter: false },
  { values: [0, 40, 0], scale: 150, lessIsBetter: true },         // of the 150 runs: the bar is its true share
  { values: [null, 3, 0], scale: 24, lessIsBetter: true },
];

/** "Tested and measured": the visitor picks a question and compares the three, with bars and plain numbers. */
@Component({
  selector: 'app-results',
  template: `
    <div class="seg wrap" role="group" [attr.aria-label]="t().heading[0]">
      @for (q of t().questions; track $index) {
        <button type="button" [class.on]="asked() === $index" [attr.aria-pressed]="asked() === $index" (click)="asked.set($index)">{{ q.tab }}</button>
      }
    </div>
    <p class="results-question" aria-live="polite">{{ t().questions[asked()].question }}
      <span>{{ data().lessIsBetter ? t().less : t().more }}</span></p>
    <ul class="bars">
      @for (who of t().who; track $index) {
        <li [class.anchor]="$index === 2">
          <div class="bars-who"><b>{{ who.title }}</b><span>{{ who.text }}</span></div>
          <div class="bars-track" aria-hidden="true"><i [style.width.%]="width($index)" [class.bad]="bad($index)"></i></div>
          <div class="bars-value" [class.bad]="bad($index)" [class.good]="good($index)">
            @if (data().values[$index] === null) { <span class="bars-missing">{{ t().missing }}</span> }
            @else { <b>{{ data().values[$index] }}</b> {{ t().questions[asked()].unit }} }
          </div>
        </li>
      }
    </ul>
    <p class="fine">{{ t().foot }} <a [href]="tests">{{ t().link }}</a></p>
  `,
})
export class Results {
  readonly t = input.required<Copy['results']>();
  readonly asked = signal(0);
  readonly data = computed(() => NUMBERS[this.asked()]);
  readonly tests = TESTS_URL;

  width(i: number): number {
    const value = this.data().values[i];
    return value === null ? 0 : Math.min(100, (100 * value) / this.data().scale);
  }

  /** A count of something bad that happened (when fewer is better). */
  bad(i: number): boolean {
    return this.data().lessIsBetter && (this.data().values[i] ?? 0) > 0;
  }

  /** The best answer to the question: the most when more is better, none when fewer is better. */
  good(i: number): boolean {
    const { values, lessIsBetter } = this.data(), value = values[i];
    if (value === null) return false;
    return lessIsBetter ? value === 0 : value === Math.max(...values.map((v) => v ?? 0));
  }
}
