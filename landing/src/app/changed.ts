import { Component, input, signal } from '@angular/core';

import { Copy } from './copy';

/**
 * "Websites change. It adjusts.": the visitor switches a small order page between how it was and how it is
 * after a redesign (the button moves and changes shape). An ordinary robot, which memorised the button's
 * place, breaks; ANCHOR, which looks for what the button is, finds it again.
 */
@Component({
  selector: 'app-changed',
  template: `
    <div class="changed">
      <div class="changed-page">
        <div class="seg" role="group" [attr.aria-label]="t().heading[0]">
          <button type="button" [class.on]="!moved()" [attr.aria-pressed]="!moved()" (click)="moved.set(false)">{{ t().before }}</button>
          <button type="button" [class.on]="moved()" [attr.aria-pressed]="moved()" (click)="moved.set(true)">{{ t().after }}</button>
        </div>
        <div class="site" [class.moved]="moved()" aria-hidden="true">
          <div class="site-bar"><i></i>{{ t().order }}</div>
          <div class="site-body order">
            <div class="order-head">
              <div><b>{{ t().order }}</b><span>{{ t().delivered }}</span></div>
              @if (moved()) { <span class="site-btn round found">{{ t().invoice }}</span> }
            </div>
            <div class="order-lines"><i></i><i></i><i></i></div>
            <div class="order-foot">
              @if (!moved()) { <span class="site-btn found">{{ t().invoice }}</span> } @else { <span class="order-ghost"></span> }
              <span class="site-link">{{ t().help }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="changed-results" aria-live="polite">
        <div class="result" [class.bad]="moved()">
          <h3>{{ t().robot }}</h3>
          <p class="result-how">{{ t().robotHow }}</p>
          <p class="result-what">{{ moved() ? t().robotBroken : t().robotOk }}</p>
        </div>
        <div class="result good">
          <h3>{{ t().anchor }}</h3>
          <p class="result-how">{{ t().anchorHow }}</p>
          <p class="result-what">{{ moved() ? t().anchorChanged : t().anchorOk }}</p>
        </div>
      </div>
    </div>
  `,
})
export class Changed {
  readonly t = input.required<Copy['changes']>();
  readonly moved = signal(false);
}
