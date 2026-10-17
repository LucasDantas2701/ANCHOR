import { Component, HostListener, OnDestroy, OnInit, inject, input, output, signal } from '@angular/core';

import { JOB_CLASS, JOB_WORDS, JobState, Runs } from '../api';

/** The browser, live, in a window over the run: shown only while it is open. */
@Component({
  selector: 'app-live',
  template: `
    <div class="screen" role="img" [attr.aria-label]="'The browser, live: ' + jobWords[state()]">
      @if (src()) { <img [src]="src()" alt=""> }
      @else { <p class="muted">{{ ended() ? 'The run ended before the browser could be shown.' : 'Waiting for the browser…' }}</p> }
    </div>
    <p class="foot muted">{{ ended() ? 'The run has ended: this is the last thing the browser showed.' : 'Live. Closing this view does not stop the run.' }}</p>
  `,
  styles: [`
    :host { display: grid; grid-template-rows: 1fr auto; min-height: 0; min-width: 0; }
    .screen { display: grid; place-items: center; background: var(--surface-sunken); border: 1px solid var(--border);
              border-radius: var(--radius-md); overflow: hidden; min-height: 0; }
    .screen img { display: block; width: 100%; height: 100%; object-fit: contain; }
    .foot { margin: 0; padding: var(--space-2) 2px 0; font-size: 12px; }
  `],
})
export class LiveView implements OnInit, OnDestroy {
  private runs = inject(Runs);
  run = input.required<number>();
  state = input.required<JobState>();
  ended = input(false);
  close = output<void>();
  src = signal<string | null>(null);
  jobWords = JOB_WORDS; jobClass = JOB_CLASS;
  private last = 0;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private alive = true;

  @HostListener('document:keydown.escape') onEscape() { this.close.emit(); }

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
