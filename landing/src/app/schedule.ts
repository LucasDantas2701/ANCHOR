import { Component, computed, input, signal } from '@angular/core';

import { Copy, Lang } from './copy';

const HOURS = Array.from({ length: 17 }, (_, i) => `${String(i + 6).padStart(2, '0')}:00`);     // 06:00 to 22:00

/**
 * "Build a schedule": the visitor picks the days and the time, and the page writes the schedule as ANCHOR's
 * interface does ("Monday to Friday at 08:00") and says when the next run would be.
 */
@Component({
  selector: 'app-schedule',
  template: `
    <div class="schedule">
      <p class="schedule-title" id="schedule-title">{{ t().build }}</p>
      <div class="schedule-controls">
        <div class="schedule-days" role="group" aria-labelledby="schedule-title">
          @for (day of t().days; track $index) {
            <button type="button" [class.on]="days()[$index]" [attr.aria-pressed]="days()[$index]" [attr.aria-label]="t().dayNames[$index]"
                    (click)="toggle($index)">{{ day }}</button>
          }
        </div>
        <label class="schedule-time">{{ t().at }}
          <select [value]="time()" (change)="time.set($any($event.target).value)">
            @for (hour of hours; track hour) { <option [value]="hour" [selected]="hour === time()">{{ hour }}</option> }
          </select>
        </label>
      </div>
      <p class="schedule-sentence" aria-live="polite">{{ sentence() }}</p>
      @if (next()) { <p class="schedule-next">{{ t().next }} {{ next() }}</p> }
    </div>
  `,
})
export class Schedule {
  readonly t = input.required<Copy['repeat']>();
  readonly lang = input.required<Lang>();

  readonly hours = HOURS;
  readonly days = signal([true, true, true, true, true, false, false]);      // Monday first
  readonly time = signal('08:00');

  readonly sentence = computed(() => {
    const t = this.t(), on = this.days(), at = `${t.at} ${this.time()}`;
    const chosen = t.dayNames.filter((_, i) => on[i]);
    if (!chosen.length) return t.none;
    if (chosen.length === 7) return `${t.everyDay}, ${at}`;
    if (on.slice(0, 5).every(Boolean) && !on[5] && !on[6]) return `${t.weekdays}, ${at}`;
    const list = chosen.length === 1 ? chosen[0] : `${chosen.slice(0, -1).join(', ')} ${t.and} ${chosen[chosen.length - 1]}`;
    return `${t.onDays} ${list}, ${at}`;
  });

  /** The next day and time the schedule would run, counted from now on the visitor's clock. */
  readonly next = computed(() => {
    const on = this.days(), [hour, minute] = this.time().split(':').map(Number), now = new Date();
    for (let ahead = 0; ahead <= 7; ahead++) {
      const when = new Date(now.getFullYear(), now.getMonth(), now.getDate() + ahead, hour, minute);
      if (on[(when.getDay() + 6) % 7] && when > now) {
        const day = new Intl.DateTimeFormat(this.lang() === 'pt' ? 'pt-BR' : 'en-GB', { weekday: 'long', day: 'numeric', month: 'long' }).format(when);
        return `${day}, ${this.t().at} ${this.time()}`;
      }
    }
    return '';
  });

  toggle(index: number): void {
    this.days.update((all) => all.map((value, i) => (i === index ? !value : value)));
  }
}
