# The synthetic set (08/10/2026): provenance

The synthetic closed set's 80 requests are in `../plans/holdout_tasks.json`; how they were generated
is in `../README.md` ("How it was built"). This folder keeps what documents their generation.

- `conversas/conversa_chatgpt.png`: the ChatGPT conversation of 08/10/2026 that generated 26 of the
  requests (sheet B). It shows the message sent with `pedidos_assistente.zip` attached (with the added line
  "2 pedidos por pagina"), the reply ("2 pedidos para cada uma das 13 páginas", in each page's
  language; the reply notes that the LEIA-ME asked for 18 and it followed the later instruction),
  and, in the same conversation on 21/10/2026, its answer about the model used: GPT-5.6 Luna.
  Kept as it was captured.
- `planilhas/`: the three sheets the AIs returned, kept byte for byte and named by their letter in
  the tasks file and their generator (A and C: the two Claudes; B: the ChatGPT). The mapping and
  what the comparison found are in `../README.md` ("How it was built").
- `SHA256SUMS`: the hashes of the sheets and of the capture.
