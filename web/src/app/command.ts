/**
 * A request pasted as a terminal command ("python -m anchor.agent "..." --url ...") is not a request:
 * the planner would read the command itself. This finds the request and the page inside it.
 */
export interface FromCommand { request: string; url: string; }

const COMMAND = /^\s*(?:py(?:thon)?3?\s+-m\s+anchor(?:\.\w+)*|anchor(?:\.\w+)*)\b|\s--(?:url|profile|automation|browser-profile)\b/;

export function fromCommand(text: string): FromCommand | null {
  if (!text || !COMMAND.test(text)) return null;
  const quoted = text.match(/"([^"]+)"|“([^”]+)”|'([^']+)'/);
  const url = text.match(/--url[ =]+("([^"]+)"|'([^']+)'|(\S+))/);
  return {
    request: quoted ? (quoted[1] || quoted[2] || quoted[3]).trim() : '',
    url: url ? (url[2] || url[3] || url[4] || '').trim() : '',
  };
}
