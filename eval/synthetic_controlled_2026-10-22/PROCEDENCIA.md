# Amostra sintética controlada — procedência

Terceira origem do conjunto fechado de tarefas: `synthetic_controlled`.
Conjunto FECHADO: ninguém olha o comportamento do sistema nestes pedidos, e nada roda neles antes da rodada final da 1.0.0.

## Como foi gerada

- **Data:** 22/10/2026.
- **Geradores** (uma conversa nova por gerador, sem histórico do projeto):
  - ChatGPT, modelo GPT-5.6 Luna → `planilhas/chatgpt.csv`, `conversas/conversa_chatgpt.png`
  - Claude Sonnet 5.5, esforço médio, conta 1 → `planilhas/claude_1.csv`, `conversas/conversa_claude_1.png`
  - Claude Sonnet 5.5, esforço médio, conta 2 → `planilhas/claude_2.csv`, `conversas/conversa_claude_2.png`
- **Material:** `pacote/pedidos_controlado.zip`, anexado. Ele contém as 9 páginas da coleta humana (as mesmas publicadas em `lucasdantas2701.github.io/web-pages-study/`), o LEIA-ME com as mesmas instruções do Google Forms da coleta humana e a planilha com 14 linhas.
- **Mensagem:** a mesma de 08/10, mudando só o tempo (15 minutos). Não houve a instrução extra de "2 pedidos por página"; a quantidade estava no LEIA-ME.
- **Geração:** uma vez por gerador, sem correção, descarte ou nova tentativa. As planilhas estão como foram devolvidas (os hashes estão em `SHA256SUMS`).
- **Total:** 42 pedidos, 14 por gerador, todos em português, nas linhas previstas (P01–P09).

## Ocorrências registradas

1. **O ChatGPT não viu as páginas.** Ele informou que não conseguiu renderizar as páginas e que os pedidos "ficaram genéricos, baseados nos nomes dos arquivos" (ver a captura). Os pedidos dele não citam elementos reais das páginas.
2. **Os dois Claudes não abriram o código.** Fizeram capturas de tela das páginas e não clicaram em nada: viram só a tela inicial.
3. **Defeito no pacote.** O cabeçalho de `pedidos.csv` no pacote tinha o texto literal `\xef\xbb\xbf` antes de "pagina", por erro na geração do arquivo. O `chatgpt.csv` manteve esse texto no cabeçalho. Os dois Claudes devolveram o cabeçalho correto, e o Claude da conta 1 relatou o defeito. Não afeta o conteúdo dos pedidos. Quem ler as planilhas deve tratar o cabeçalho.
4. **Possível influência dos exemplos do LEIA-ME.** O `claude_2.csv` (P07) repete palavra por palavra o exemplo "Cancela o pedido que ainda não saiu". Os dois Claudes pediram para reservar a sala Amazonas, que aparece no outro exemplo.

## Decisão de análise (tomada em 22/10/2026, antes de qualquer anotação ou execução)

- Os 42 pedidos ficam no repositório e no artigo.
- Os resultados saem de duas formas: (a) os 42; (b) só os 28 dos dois Claudes, como **análise de sensibilidade**.
- A exclusão do ChatGPT em (b) foi decidida **depois** da coleta. O motivo é objetivo e foi registrado pela própria ferramenta na conversa (ocorrência 1), não com base em resultados. Isso é declarado no artigo.

## Correções de 08/11/2026

Registradas depois de uma conferência dos documentos com os arquivos (o relatório de divergências de 08/11/2026). As frases acima ficam como foram escritas em 22/10; valem as correções abaixo.

1. **O LEIA-ME do pacote** (item "Material"). O LEIA-ME que foi em `pacote/pedidos_controlado.zip` não tinha exatamente as mesmas instruções do Google Forms: era a versão de antes da revisão das instruções da coleta humana, com os exemplos "quero reservar a sala Amazonas para amanhã às 10h" e "cancela o pedido que ainda não saiu", e sem o exemplo da pizzaria. Base: o próprio `LEIA-ME.txt` de dentro do zip, cujo hash confere com `SHA256SUMS`; o autor confirmou, em 08/11/2026, que esse zip é o arquivo anexado às três conversas. Isso é coerente com a ocorrência 4.
2. **Os pedidos do ChatGPT** (ocorrência 1). A frase "Os pedidos dele não citam elementos reais das páginas" é forte demais. O que vale: ele informou que não conseguiu renderizar as páginas e que os pedidos ficaram genéricos, baseados nos nomes dos arquivos; na contagem de 23/10/2026 (`python -m eval.closed_sets page-items synthetic_controlled`, que imprime só contagens), 8 dos 14 pedidos dele têm ao menos uma palavra do texto visível da sua página que não aparece em nenhuma outra página do conjunto, contra 14 de 14 de cada Claude. A decisão de análise acima não muda: ela se baseia no que a ferramenta declarou na conversa.
3. **Como conferir os hashes.** `SHA256SUMS` tem quebras de linha CRLF, mantidas porque esta pasta guarda os arquivos byte a byte; por isso `sha256sum -c SHA256SUMS` pode falhar mesmo com os arquivos intactos. Para conferir: `tr -d '\r' < SHA256SUMS | sha256sum -c` (conferido em 08/11/2026: os quatro arquivos batem).
