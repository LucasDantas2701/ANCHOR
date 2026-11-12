import { Component, computed, input, signal } from '@angular/core';

import { Copy } from './copy';

type Who = 'plain' | 'anchor';

/**
 * "It only does what you asked": a shop page hides an order addressed to an AI. The visitor chooses who
 * reads it (an AI with no protection, or ANCHOR) and sees what each one does. Scripted; the numbers under
 * it are the measured ones (the injection suite: 3 of 24 runs hijacked against none).
 */
@Component({
  selector: 'app-trick',
  template: `
    <div class="trick">
      <div class="site" aria-hidden="true">
        <div class="site-bar"><i></i>{{ t().product }}</div>
        <div class="site-body">
          <div class="site-product"><b>{{ t().product }}</b><span>{{ t().price }}</span></div>
          <span class="site-btn" [class.pressed]="added()">{{ t().add }}</span>
          <p class="site-note" [class.hot]="noticed()">{{ t().hidden }}</p>
          <span class="site-btn danger" [class.fired]="deleted()">{{ t().remove }}</span>
        </div>
      </div>

      <div class="trick-side">
        <p class="trick-request"><span>{{ t().yours }}</span>{{ t().request }}</p>
        <div class="seg" role="group" [attr.aria-label]="t().title">
          <button type="button" [class.on]="who() === 'plain'" [attr.aria-pressed]="who() === 'plain'" (click)="choose('plain')">{{ t().plain }}</button>
          <button type="button" [class.on]="who() === 'anchor'" [attr.aria-pressed]="who() === 'anchor'" (click)="choose('anchor')">{{ t().anchor }}</button>
        </div>
        <button type="button" class="btn-go" (click)="run()">{{ shown() ? t().again : t().run }}</button>
        <ol class="log-steps" aria-live="polite">
          @for (step of steps(); track $index) {
            @if ($index < shown()) { <li [class]="who() === 'plain' ? 's-denied' : 's-checked'"><span class="log-text">{{ step }}</span></li> }
          }
        </ol>
        @if (ended()) { <p class="trick-end" [class.bad]="who() === 'plain'" role="status">{{ who() === 'plain' ? t().plainEnd : t().anchorEnd }}</p> }
      </div>
    </div>
    <p class="proof">{{ t().proof }}</p>
  `,
})
export class Trick {
  readonly t = input.required<Copy['control']['trick']>();

  readonly who = signal<Who>('plain');
  readonly shown = signal(0);
  readonly ended = signal(false);
  readonly steps = computed(() => (this.who() === 'plain' ? this.t().plainSteps : this.t().anchorSteps));
  readonly noticed = computed(() => this.who() === 'plain' && this.shown() >= 1);
  readonly deleted = computed(() => this.who() === 'plain' && this.shown() >= 2);
  readonly added = computed(() => this.who() === 'anchor' && this.shown() >= 2);

  private turn = 0;
  private readonly still = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

  choose(who: Who): void {
    this.turn++;
    this.who.set(who);
    this.shown.set(0);
    this.ended.set(false);
  }

  async run(): Promise<void> {
    const turn = ++this.turn;
    this.shown.set(0);
    this.ended.set(false);
    for (let i = 1; i <= this.steps().length; i++) {
      await new Promise((done) => setTimeout(done, this.still ? 0 : 650));
      if (turn !== this.turn) return;
      this.shown.set(i);
    }
    await new Promise((done) => setTimeout(done, this.still ? 0 : 450));
    if (turn === this.turn) this.ended.set(true);
  }
}
