# Pages of the human collection

These are the pages that the people of the human closed set saw when they wrote their requests
(the collection's site publishes exactly these files). The human set's tasks run on them; the
synthetic set (`plans/holdout_tasks.json`) still runs on the original pages it was written on.

They were made from the 13 pages of the synthetic set's package, for a collection answered in
Portuguese, before any request was collected:

| Page here | Made from | Change |
|---|---|---|
| `blog.html` | `../holdout_blog.html` | texts translated to Portuguese |
| `rh.html` | `../holdout_hr.html` | texts translated to Portuguese (dates as "12 out") |
| `loja.html` | `../store.html` | texts translated to Portuguese (prices in reais) |
| `reservas.html` | `../holdout_booking.html` | none (already in Portuguese) |
| `suporte.html` | `../holdout_helpdesk.html` | none (already in Portuguese) |
| `vagas.html` | `../jobs.html` | none (already in Portuguese) |
| `pedidos.html` | `../orders.html` | none (already in Portuguese) |
| `cadastro.html` | `../registration.html` | none (already in Portuguese) |
| `usuarios.html` | `../users.html` | none (already in Portuguese) |

The four English pages that have a Portuguese twin (`jobs_en`, `orders_en`, `registration_en`,
`users_en`) were left out. In every page, only texts changed: the tags, their order, ids, classes,
roles and types are the original page's (checked element by element). All of them load
`colecao.css`, a plain style (fonts, spacing, colours and borders only; nothing hidden, overlaid or
moved: every actionable element stays visible and receives its own click, checked with and without
it). `feedback.js` is the original without its opening comment.
