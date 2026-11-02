import { TrPipe, tr } from '../i18n';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { Api, AutomationSummary, Schedule, ScheduleEntry, ScheduleWhen, apiError, isoDate } from '../api';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const STATE: Record<string, [string, string]> = {
  checked: ['Done', 'checked'], not_done: ['Not done', 'refused'], error: ['Could not run', 'refused'], stopped: ['Stopped', 'waiting'],
  missed: ['Missed', 'waiting'], skipped: ['Skipped', ''], nothing: ['Nothing new', ''], running: ['Running', 'accent'],
};

/** Schedules: an automation run by itself at set times, while ANCHOR is open. */
@Component({
  selector: 'app-schedules',
  imports: [FormsModule, RouterLink, TrPipe],
  template: `
    <p class="eyebrow">{{ 'Run by themselves' | tr }}</p>
    <h1 class="title">{{ 'Schedules' | tr }}</h1>
    <div class="card limit" role="note">
      <b>{{ 'ANCHOR must be open for a schedule to run.' | tr }}</b> {{ 'If it is closed at the time, that run does not happen, and it is not run later: when ANCHOR opens again, it tells you which ones were missed, and they show here as' | tr }} <i>{{ 'Missed' | tr }}</i>.
    </div>
    <p class="muted lead">{{ 'A schedule runs an automation with no one present. Only an automation that already had one clean run with you can be scheduled; with no one present, nothing is fixed or asked, only the sensitive actions you already allowed are done, and only the saved logins with “Use in scheduled runs” are used.' | tr }}</p>

    <form class="card pad form" (ngSubmit)="save()">
      <p class="eyebrow">{{ (editing() ? 'Edit the schedule' : 'New schedule') | tr }}</p>
      <div class="row">
        <div class="field"><label for="s-auto">{{ 'Automation' | tr }}</label>
          <select id="s-auto" name="auto" [(ngModel)]="automation" [disabled]="!!editing()">
            <option value="" disabled>{{ 'Choose an automation' | tr }}</option>
            @for (a of automations(); track a.name) {
              <option [value]="a.name" [disabled]="!a.proven">{{ a.name }}{{ a.proven ? '' : ' (needs one clean run with you first)' }}</option>
            }
          </select></div>
      </div>
      @if (chosen()?.parameters?.length) {
        <div class="row">
          <div class="field wide"><label for="s-sheet">{{ 'Spreadsheet (read at run time)' | tr }}</label>
            <input id="s-sheet" name="sheet" [(ngModel)]="sheet" [placeholder]="'C:\\\\Users\\\\you\\\\Documents\\\\new-employees.xlsx' | tr">
            <span class="hint">{{ 'The full path of a CSV or .xlsx file on this computer, with a column for each value: {cols}.' | tr: { cols: chosen()?.parameters?.join(', ') } }}
              {{ 'At run time, ANCHOR reads it as it is then, checks it, and runs only the rows this schedule did not do yet.' | tr }}</span></div>
          <div class="field small"><label for="s-max">{{ 'At most, rows per run' | tr }}</label>
            <input id="s-max" name="max" type="number" min="1" max="500" [(ngModel)]="maxRows">
            <span class="hint">{{ 'More new rows than this: nothing runs, and it says so.' | tr }}</span></div>
        </div>
      }
      <div class="kinds" role="radiogroup" [attr.aria-label]="'When it runs' | tr">
        @for (k of kinds; track k.id) {
          <label class="kind" [class.on]="kind === k.id"><input type="radio" name="kind" [value]="k.id" [(ngModel)]="kind">{{ k.label | tr }}</label>
        }
      </div>
      <div class="row">
        @switch (kind) {
          @case ('once') { <div class="field"><label for="s-at">{{ 'Date and time' | tr }}</label><input id="s-at" name="at" type="datetime-local" [(ngModel)]="at"></div> }
          @case ('monthly') {
            <div class="field small"><label for="s-day">{{ 'Day of the month' | tr }}</label><input id="s-day" name="day" type="number" min="1" max="31" [(ngModel)]="day">
              <span class="hint">{{ "29 to 31: the month's last day when it is shorter." | tr }}</span></div>
          }
          @case ('every') {
            <div class="field small"><label for="s-every">{{ 'Every' | tr }}</label><input id="s-every" name="every" type="number" min="1" [(ngModel)]="every"></div>
            <div class="field small"><label for="s-unit">&nbsp;</label>
              <select id="s-unit" name="unit" [(ngModel)]="unit"><option value="minutes">{{ 'minutes' | tr }}</option><option value="hours">{{ 'hours' | tr }}</option><option value="days">{{ 'days' | tr }}</option></select></div>
            <div class="field small"><label for="s-start">{{ 'Starting at' | tr }}</label><input id="s-start" name="start" type="time" [(ngModel)]="start"></div>
          }
        }
        @if (kind !== 'once' && kind !== 'every') { <div class="field small"><label for="s-time">{{ 'At' | tr }}</label><input id="s-time" name="time" type="time" [(ngModel)]="time"></div> }
      </div>
      @if (kind === 'weekly' || kind === 'every') {
        <div class="days" role="group" [attr.aria-label]="'Days of the week' | tr">
          @if (kind === 'every') { <label class="check"><input type="checkbox" name="onDays" [(ngModel)]="onDays"> {{ 'Only on some days' | tr }}</label> }
          @if (kind === 'weekly' || onDays) {
            @for (d of dayNames; track $index) {
              <label class="day" [class.on]="days.includes($index)"><input type="checkbox" [checked]="days.includes($index)" (change)="toggleDay($index)">{{ d | tr }}</label>
            }
          }
        </div>
      }
      @if (kind === 'every') {
        <div class="row">
          <label class="check"><input type="checkbox" name="win" [(ngModel)]="useWindow"> {{ 'Only between' | tr }}</label>
          @if (useWindow) {
            <input class="t" name="w1" type="time" [(ngModel)]="win1"> <span class="muted">{{ 'and' | tr }}</span> <input class="t" name="w2" type="time" [(ngModel)]="win2">
          }
        </div>
      }
      <div class="go">
        <button class="btn primary" type="submit" [disabled]="!automation">{{ (editing() ? 'Save changes' : 'Add schedule') | tr }}</button>
        @if (editing()) { <button class="btn" type="button" (click)="cancelEdit()">{{ 'Cancel' | tr }}</button> }
      </div>
      @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    </form>

    <section>
      @for (s of list(); track s.id) {
        <article class="card item" [class.off]="!s.enabled">
          <header>
            <a class="name" [routerLink]="['/automations', s.automation]">{{ s.automation }}</a>
            <span class="words">{{ s.words }}</span>
            <span class="grow"></span>
            <label class="check small"><input type="checkbox" [checked]="s.enabled" (change)="enable(s, $any($event.target).checked)"> {{ 'On' | tr }}</label>
          </header>
          <p class="meta">
            @if (s.enabled && s.next_run) { {{ 'Next:' | tr }} <b>{{ isoDate(s.next_run) }}</b> } @else if (!s.enabled) { {{ 'Turned off' | tr }} } @else { {{ 'No next time' | tr }} }
            @if (s.sheet) { <span class="muted"> {{ '· reads' | tr }} <span class="mono">{{ s.sheet }}</span>{{ ', at most {n} rows' | tr: { n: s.max_rows } }}</span> }
          </p>
          @if (s.last) {
            <p class="meta"><span [class]="'badge ' + stateClass(s.last.state)">{{ stateWord(s.last.state) }}</span>
              <span class="muted"> {{ isoDate(s.last.due) }}@if (s.last.message) { · {{ s.last.message | tr }} }</span></p>
          }
          <div class="acts">
            <button class="btn small" type="button" (click)="toggleHistory(s)">{{ (open() === s.id ? 'Hide history' : 'History') | tr }}</button>
            <button class="btn small" type="button" (click)="startEdit(s)">{{ 'Edit' | tr }}</button>
            @if (s.sheet) { <button class="btn small" type="button" (click)="forgetRows(s)">{{ 'Do every row again' | tr }}</button> }
            <button class="btn small" type="button" (click)="remove(s)">{{ 'Delete' | tr }}</button>
          </div>
          @if (open() === s.id) {
            <table class="hist">
              <thead><tr><th>{{ 'Due' | tr }}</th><th>{{ 'Result' | tr }}</th><th>{{ 'What happened' | tr }}</th></tr></thead>
              <tbody>@for (h of history(); track h.id) {
                <tr><td class="muted">{{ isoDate(h.due) }}</td><td><span [class]="'badge ' + stateClass(h.state)">{{ stateWord(h.state) }}</span></td>
                  <td class="muted">{{ h.message | tr }}@if (h.run) { · <a [routerLink]="['/runs', h.run]">{{ 'run' | tr }}</a> }</td></tr>
              } @empty { <tr><td colspan="3" class="muted">{{ 'Nothing yet.' | tr }}</td></tr> }</tbody>
            </table>
          }
        </article>
      } @empty { <div class="card pad muted">{{ 'No schedules yet.' | tr }}</div> }
    </section>
  `,
  styles: [`
    .limit { padding: var(--space-4) var(--space-6); border-color: var(--waiting); margin: var(--space-4) 0; max-width: 1080px; font-size: 14px; line-height: 1.5; }
    .lead { max-width: 820px; margin: 0 0 var(--space-6); }
    .form { display: grid; gap: var(--space-4); max-width: 1080px; margin-bottom: var(--space-8); }
    .form .eyebrow { margin: 0; }
    .row { display: flex; flex-wrap: wrap; gap: var(--space-4); align-items: flex-end; }
    .field { display: grid; gap: 6px; min-width: 240px; }
    .field.wide { flex: 1; min-width: 360px; } .field.small { min-width: 120px; }
    .field label { font: 500 12px/16px var(--font-mono); letter-spacing: .12em; text-transform: uppercase; color: var(--accent); }
    input, select { background: var(--surface-page); color: var(--ink); border: 1px solid var(--border-strong); border-radius: var(--radius-sm);
                    padding: 9px 12px; font: 400 14px/20px var(--font-sans); }
    input.t { width: 120px; }
    .hint { font-size: 12px; color: var(--ink-muted); max-width: 640px; }
    .kinds, .days { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .kind, .day { border: 1px solid var(--border-strong); border-radius: var(--radius-full); padding: 6px 14px; font-size: 13px; cursor: pointer; color: var(--ink-muted); }
    .kind.on, .day.on { border-color: var(--lime); color: var(--ink); }
    .kind input, .day input { display: none; }
    .check { display: flex; gap: 8px; align-items: center; font-size: 13px; color: var(--ink-muted); }
    .go { display: flex; gap: var(--space-3); }
    section { max-width: 1080px; }
    .item { padding: var(--space-4) var(--space-6); margin-bottom: var(--space-4); display: grid; gap: 8px; }
    .item.off { opacity: .6; }
    .item header { display: flex; align-items: center; gap: var(--space-4); flex-wrap: wrap; }
    .name { font-weight: 600; color: var(--ink); }
    .words { color: var(--ink-muted); font-size: 14px; }
    .grow { flex: 1; }
    .meta { margin: 0; font-size: 13.5px; }
    .acts { display: flex; gap: 6px; flex-wrap: wrap; }
    .btn.small { padding: 4px 10px; font-size: 12.5px; }
    .hist { border-collapse: collapse; font-size: 13px; width: 100%; }
    .hist th, .hist td { padding: 6px 10px; border-bottom: 1px solid var(--border); text-align: left; }
    .pad { padding: var(--space-4) var(--space-6); }
    .error { color: var(--refused); margin: 0; }
  `],
})
export class SchedulesPage {
  private api = inject(Api);
  private route = inject(ActivatedRoute);
  isoDate = isoDate;
  dayNames = DAYS;
  kinds = [{ id: 'daily', label: 'Every day' }, { id: 'weekly', label: 'Days of the week' }, { id: 'monthly', label: 'A day of the month' },
           { id: 'once', label: 'Once' }, { id: 'every', label: 'Custom: every N minutes, hours or days' }];
  automations = signal<AutomationSummary[]>([]);
  list = signal<Schedule[]>([]);
  history = signal<ScheduleEntry[]>([]);
  open = signal<number | null>(null);
  editing = signal<number | null>(null);
  error = signal('');
  automation = ''; sheet = ''; maxRows = 50;
  kind: ScheduleWhen['kind'] = 'daily';
  at = ''; time = '08:00'; day = 1; days: number[] = [0, 1, 2, 3, 4];
  every = 2; unit: 'minutes' | 'hours' | 'days' = 'hours'; start = '08:00'; onDays = false; useWindow = false; win1 = '08:00'; win2 = '18:00';

  constructor() {
    this.api.automations().subscribe(a => this.automations.set(a));
    this.load();
    this.route.queryParamMap.subscribe(q => { const name = q.get('automation'); if (name) this.automation = name; });
  }
  chosen() { return this.automations().find(a => a.name === this.automation) ?? null; }
  load() { this.api.schedules().subscribe({ next: s => this.list.set(s), error: e => this.error.set(apiError(e, tr('The schedules could not be loaded.'))) }); }
  toggleDay(d: number) { this.days = this.days.includes(d) ? this.days.filter(x => x !== d) : [...this.days, d].sort(); }
  when(): ScheduleWhen {
    switch (this.kind) {
      case 'once': return { kind: 'once', at: this.at };
      case 'daily': return { kind: 'daily', time: this.time };
      case 'weekly': return { kind: 'weekly', days: this.days, time: this.time };
      case 'monthly': return { kind: 'monthly', day: Number(this.day), time: this.time };
      default: return { kind: 'every', every: Number(this.every), unit: this.unit, start: this.start,
                        window: this.useWindow ? [this.win1, this.win2] : null, days: this.onDays ? this.days : null };
    }
  }
  save() {
    this.error.set('');
    const id = this.editing();
    const done = { next: () => { this.cancelEdit(); this.load(); }, error: (e: unknown) => this.error.set(apiError(e, tr('The schedule could not be saved.'))) };
    if (id) this.api.editSchedule(id, this.when(), this.sheet, Number(this.maxRows)).subscribe(done);
    else this.api.addSchedule(this.automation, this.when(), this.sheet, Number(this.maxRows)).subscribe(done);
  }
  startEdit(s: Schedule) {
    this.editing.set(s.id); this.automation = s.automation; this.sheet = s.sheet; this.maxRows = s.max_rows;
    const w = s.when; this.kind = w.kind;
    if (w.at) this.at = w.at; if (w.time) this.time = w.time; if (w.day) this.day = w.day;
    if (w.days) { this.days = [...w.days]; this.onDays = w.kind === 'every'; }
    if (w.kind === 'every') { this.every = w.every ?? 2; this.unit = w.unit ?? 'hours'; this.start = w.start ?? '08:00';
                              this.useWindow = !!w.window; if (w.window) { this.win1 = w.window[0]; this.win2 = w.window[1]; } }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  cancelEdit() { this.editing.set(null); this.automation = ''; this.sheet = ''; this.maxRows = 50; this.kind = 'daily'; }
  enable(s: Schedule, on: boolean) { this.api.enableSchedule(s.id, on).subscribe({ next: () => this.load(), error: e => this.error.set(apiError(e, tr('This could not be changed.'))) }); }
  toggleHistory(s: Schedule) {
    if (this.open() === s.id) { this.open.set(null); return; }
    this.open.set(s.id); this.history.set([]);
    this.api.scheduleHistory(s.id).subscribe(h => this.history.set(h));
  }
  forgetRows(s: Schedule) {
    if (!confirm(tr('Forget which rows this schedule already did? Its next run does every row of the spreadsheet again.'))) return;
    this.api.forgetScheduleRows(s.id).subscribe({ next: () => this.load(), error: e => this.error.set(apiError(e, tr('This could not be done.'))) });
  }
  remove(s: Schedule) {
    if (!confirm(tr('Delete the schedule of {name} ({when})? Its history goes too.', { name: s.automation, when: s.words }))) return;
    this.api.deleteSchedule(s.id).subscribe({ next: () => this.load(), error: e => this.error.set(apiError(e, tr('The schedule could not be deleted.'))) });
  }
  stateWord(state: string) { return tr((STATE[state] ?? [state, ''])[0]); }
  stateClass(state: string) { return (STATE[state] ?? ['', ''])[1]; }
}
