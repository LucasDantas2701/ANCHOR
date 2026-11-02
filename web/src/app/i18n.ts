import { Pipe, PipeTransform, signal } from '@angular/core';

import { PT } from './i18n-pt';

/** The interface's language: Portuguese or English. It starts as the computer's and changes in Settings. */
export type Lang = 'en' | 'pt';

function initial(): Lang {
  try {
    const saved = localStorage.getItem('anchor-lang');
    if (saved === 'en' || saved === 'pt') return saved;
  } catch { /* no storage: the computer's language */ }
  return (navigator.language || 'en').toLowerCase().startsWith('pt') ? 'pt' : 'en';
}

export const lang = signal<Lang>(initial());
document.documentElement.lang = lang() === 'pt' ? 'pt-BR' : 'en';

export function setLang(next: Lang) {
  lang.set(next);
  try { localStorage.setItem('anchor-lang', next); } catch { /* the choice lasts this session */ }
  document.documentElement.lang = next === 'pt' ? 'pt-BR' : 'en';
}

/** The English text as the key; in Portuguese, its translation (or the English text, if there is none yet).
 *  {name} in the text takes params.name. */
export function tr(text: string, params?: Record<string, unknown>): string {
  let out = lang() === 'pt' ? (PT[text] ?? text) : text;
  if (params) for (const [k, v] of Object.entries(params)) out = out.split(`{${k}}`).join(String(v ?? ''));
  return out;
}

@Pipe({ name: 'tr', pure: false })
export class TrPipe implements PipeTransform {
  transform(text: string, params?: Record<string, unknown>): string { return tr(text, params); }
}
