import { Component, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';

@Component({
  selector: 'app-soon',
  template: `
    <p class="eyebrow">{{ what }}</p>
    <h1 class="title">Coming <em>in the next steps</em></h1>
    <p class="muted lead">This part of ANCHOR is being built. For now, it works from the command line.</p>
  `,
  styles: [`.lead { max-width: 520px; margin-top: var(--space-3); }`],
})
export class SoonPage {
  what = inject(ActivatedRoute).snapshot.data['what'] as string;
}
