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

## The form

`criar_formulario.gs` is the Google Apps Script that built the collection's Google Form, kept as it
was: it holds every text the people saw (the opening, the consent, the instructions, the help of each
field) and every question's title, which `eval/human_sample.py` reads in the export ("Pxx · Você
abriu o link desta página?", "Pxx · Pedido", "Pxx · Pedido 1", "Pxx · Pedido 2"). Before the form went
out, it was tried once (a pilot response, sent at 22/10/2026 13:18:01, which the draw leaves out);
after the pilot, only instruction texts changed, and this file is the final version.

The people's instructions differ from the ones the AIs of the `synthetic_controlled` set got: that
set's package used the LEIA-ME from before this revision, with the examples "quero reservar a sala
Amazonas para amanhã às 10h" and "cancela o pedido que ainda não saiu" and without the pizzeria
example (an order to the assistant versus the text typed in the site). The presentation differs too:
the people see a picture of each page and can open it; the AIs got the package's pictures.

