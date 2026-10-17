import { Component, ElementRef, HostListener, OnDestroy, OnInit, effect, inject, input, output, signal, viewChild } from '@angular/core';

import { JOB_CLASS, JOB_WORDS, JobState, Runs } from '../api';

/** The browser, live, in a window over the run: shown only while it is open. */
@Component({
  selector: 'app-live',
  template: `
    <div #screen class="screen" [class.control]="interactive()" [attr.tabindex]="interactive() ? 0 : null"
         [attr.aria-label]="interactive() ? 'The browser: click and type here' : 'The browser, live: ' + jobWords[state()]"
         (keydown)="key($event)" (paste)="paste($event)" (wheel)="wheel($event)">
      @if (src()) { <img #img [src]="src()" alt="" (click)="click($event)" draggable="false"> }
      @else { <p class="muted">{{ ended() ? 'The run ended before the browser could be shown.' : 'Waiting for the browser…' }}</p> }
    </div>
    @if (interactive()) {
      <p class="foot control-note">You are in control: click and type on the page. Paste with Ctrl+V. Nothing you type is kept or shown to the AI.</p>
    } @else {
      <p class="foot muted">{{ ended() ? 'The run has ended: this is the last thing the browser showed.' : 'Live. Closing this view does not stop the run.' }}</p>
    }
  `,
  styles: [`
    :host { display: grid; grid-template-rows: 1fr auto; min-height: 0; min-width: 0; }
    .screen { display: grid; place-items: center; background: var(--surface-sunken); border: 1px solid var(--border);
              border-radius: var(--radius-md); overflow: hidden; min-height: 0; }
    .screen img { display: block; width: 100%; height: 100%; object-fit: contain; user-select: none; }
    .screen.control { border: 2px solid var(--lime); cursor: pointer; }
    .screen.control:focus-visible { outline: 2px solid var(--focus); outline-offset: 3px; }
    .control-note { color: var(--checked); }
    .foot { margin: 0; padding: var(--space-2) 2px 0; font-size: 12px; }
  `],
})
export class LiveView implements OnInit, OnDestroy {
  private runs = inject(Runs);
  run = input.required<number>();
  state = input.required<JobState>();
  ended = input(false);
  interactive = input(false);
  close = output<void>();
  screen = viewChild<ElementRef<HTMLElement>>('screen');
  img = viewChild<ElementRef<HTMLImageElement>>('img');
  src = signal<string | null>(null);
  jobWords = JOB_WORDS; jobClass = JOB_CLASS;
  private last = 0;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private alive = true;

  @HostListener('document:keydown.escape') onEscape() { if (!this.interactive()) this.close.emit(); }

  constructor() {
    // When the browser waits for the person, the screen takes the keyboard at once.
    effect(() => { if (this.interactive()) setTimeout(() => this.screen()?.nativeElement.focus()); });
  }

  /** Where on the page a point of the image is (0 to 1), leaving out the bars around the picture. */
  private where(e: MouseEvent): { x: number; y: number } | null {
    const img = this.img()?.nativeElement;
    if (!img || !img.naturalWidth) return null;
    const r = img.getBoundingClientRect();
    const scale = Math.min(r.width / img.naturalWidth, r.height / img.naturalHeight);
    const w = img.naturalWidth * scale, h = img.naturalHeight * scale;
    const x = (e.clientX - r.left - (r.width - w) / 2) / w, y = (e.clientY - r.top - (r.height - h) / 2) / h;
    return x >= 0 && x <= 1 && y >= 0 && y <= 1 ? { x, y } : null;
  }

  private send(event: Record<string, unknown>) {
    if (this.interactive()) this.runs.input(this.run(), event).subscribe({ error: () => {} });
  }

  click(e: MouseEvent) {
    const at = this.where(e);
    if (at && this.interactive()) { this.send({ type: 'click', ...at }); this.screen()?.nativeElement.focus(); }
  }

  wheel(e: WheelEvent) {
    if (!this.interactive()) return;
    e.preventDefault();
    const at = this.where(e) ?? { x: 0.5, y: 0.5 };
    this.send({ type: 'scroll', ...at, dy: e.deltaY });
  }

  key(e: KeyboardEvent) {
    if (!this.interactive()) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') return;              // the paste event brings the text
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') { e.preventDefault(); this.send({ type: 'key', key: e.ctrlKey ? 'Control+a' : 'Meta+a' }); return; }
    if (e.key === 'Escape') { e.preventDefault(); this.send({ type: 'key', key: 'Escape' }); return; }
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); this.send({ type: 'text', text: e.key }); return; }
    const special = e.key === 'Tab' && e.shiftKey ? 'Shift+Tab' : e.key;
    if (['Enter', 'Tab', 'Shift+Tab', 'Backspace', 'Delete', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'].includes(special)) {
      e.preventDefault(); this.send({ type: 'key', key: special });
    }
  }

  paste(e: ClipboardEvent) {
    if (!this.interactive()) return;
    e.preventDefault();
    const text = e.clipboardData?.getData('text') ?? '';
    if (text) this.send({ type: 'text', text });
  }

  ngOnInit() { this.next(); }

  ngOnDestroy() {
    this.alive = false;
    clearTimeout(this.timer);
    const old = this.src(); if (old) URL.revokeObjectURL(old);
  }

  /** Asks for the latest picture; asking is what keeps the live view on, and stopping lets it go. */
  private next() {
    this.runs.frame(this.run(), this.last).subscribe({
      next: r => {
        if (r.status === 200 && r.body) {
          this.last = Number(r.headers.get('X-Frame') ?? this.last);
          const old = this.src();
          this.src.set(URL.createObjectURL(r.body));
          if (old) URL.revokeObjectURL(old);
        }
        this.schedule();
      },
      error: () => this.schedule(1000),
    });
  }

  private schedule(ms = 150) {
    if (this.alive && !this.ended()) this.timer = setTimeout(() => this.next(), ms);
  }
}
