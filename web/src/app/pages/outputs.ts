import { Component, OnDestroy, effect, inject, input, signal } from '@angular/core';

import { RunOutput, Runs } from '../api';

/** What a run brought back: answers, tables and lists (first rows shown), files, screenshots. */
@Component({
  selector: 'app-outputs',
  template: `
    @for (o of outputs(); track $index) {
      <article class="out" [class.wide]="o.kind === 'table' || o.kind === 'list'">
        <p class="what">{{ label(o) }}@if (o.description && o.kind !== 'screenshot') { <span class="muted"> · {{ o.description }}</span> }</p>
        @switch (o.kind) {
          @case ('text') {
            <div class="text">{{ o.text }}</div>
            <button class="btn small" type="button" (click)="copy(o.text ?? '', $index)">{{ copied() === $index ? 'Copied' : 'Copy' }}</button>
          }
          @case ('screenshot') {
            @if (images()[$index]; as url) {
              <a [href]="url" target="_blank" rel="noopener" class="shot" title="Open in full size"><img [src]="url" [alt]="'The page at the end: ' + o.description"></a>
            } @else { <p class="muted small">Loading the screenshot…</p> }
            <button class="btn small" type="button" (click)="download($index, o)">Download</button>
          }
          @case ('file') {
            <p class="mono small">{{ o.name }} <span class="muted">· {{ size(o.bytes) }}</span></p>
            <button class="btn small" type="button" (click)="download($index, o)">Download</button>
          }
          @default {
            <p class="muted small">{{ o.total }} row{{ o.total === 1 ? '' : 's' }}@if ((o.total ?? 0) > (o.rows?.length ?? 0)) {, the first {{ o.rows?.length }} shown}</p>
            <div class="scroll"><table>
              <thead><tr>@for (c of o.columns ?? []; track $index) { <th>{{ c }}</th> }</tr></thead>
              <tbody>@for (r of o.rows ?? []; track $index) { <tr>@for (cell of r; track $index) { <td>{{ cell }}</td> }</tr> }</tbody>
            </table></div>
            <button class="btn small" type="button" (click)="download($index, o)">Download CSV</button>
          }
        }
      </article>
    }
  `,
  styles: [`
    :host { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-3); width: 100%; }
    .out { border: 1px solid var(--border); border-radius: var(--radius-md); padding: var(--space-3) var(--space-4); display: grid; gap: 8px;
           align-content: start; background: var(--surface-page); min-width: 0; }
    .out.wide { grid-column: 1 / -1; }
    .what { margin: 0; font-weight: 600; font-size: 14px; }
    .text { font-size: 15px; line-height: 1.5; white-space: pre-wrap; overflow-wrap: anywhere; }
    .small { font-size: 12.5px; margin: 0; }
    .shot img { display: block; width: 100%; max-height: 260px; object-fit: cover; object-position: top; border-radius: var(--radius-sm); border: 1px solid var(--border); }
    .scroll { overflow: auto; max-height: 360px; }
    table { border-collapse: collapse; font-size: 13px; width: 100%; }
    th, td { padding: 6px 10px; border-bottom: 1px solid var(--border); text-align: left; white-space: nowrap; }
    th { position: sticky; top: 0; background: var(--surface-page); }
    .btn.small { justify-self: start; padding: 4px 10px; font-size: 12.5px; }
  `],
})
export class Outputs implements OnDestroy {
  private runs = inject(Runs);
  run = input.required<number>();
  outputs = input<RunOutput[]>([]);
  row = input(0);
  images = signal<Record<number, string>>({});
  copied = signal<number | null>(null);
  private urls: string[] = [];

  constructor() {
    effect(() => {
      this.outputs().forEach((o, i) => {
        if (o.kind !== 'screenshot' || this.images()[i]) return;
        this.runs.outputFile(this.run(), i, this.row()).subscribe(blob => {
          const url = URL.createObjectURL(blob);
          this.urls.push(url);
          this.images.set({ ...this.images(), [i]: url });
        });
      });
    });
  }
  ngOnDestroy() { this.urls.forEach(u => URL.revokeObjectURL(u)); }

  label(o: RunOutput) {
    return { text: 'Answer', table: 'Table', list: 'List', file: 'Downloaded file', screenshot: 'Screenshot of the page' }[o.kind] ?? o.kind;
  }
  size(bytes?: number) {
    const b = bytes ?? 0;
    return b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : b > 1024 ? `${Math.round(b / 1024)} KB` : `${b} bytes`;
  }
  copy(text: string, i: number) {
    navigator.clipboard?.writeText(text).then(() => { this.copied.set(i); setTimeout(() => this.copied.set(null), 1500); });
  }
  download(i: number, o: RunOutput) {
    this.runs.outputFile(this.run(), i, this.row()).subscribe(blob => {
      const url = URL.createObjectURL(blob);
      const link = Object.assign(document.createElement('a'), { href: url, download: (o.path ?? o.name ?? 'output').split(/[\\\\/]/).pop() });
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
}
