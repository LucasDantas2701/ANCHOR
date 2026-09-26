# Avaliação do Resolver (Peça 10)

Rodar, na raiz do projeto:

    python -m eval.run --offline -v     # só as páginas locais, mostrando cada caso
    python -m eval.run                  # inclui sites reais (SauceDemo)
    python -m eval.run --split test     # só o conjunto de teste
    python -m eval.run --sweep          # testa combinações de score mínimo × gap

Cada execução grava `results/<data>_<commit>.csv` (um caso por linha) e um `.json` com o resumo.

## Formato de um arquivo de casos (`cases/<site>.json`)

    {
      "site": "loja",
      "fixture": "loja.html",           // página local em fixtures/  (ou "url": "https://...")
      "setup": "saucedemo_login",       // opcional: função em setups.py
      "requires_network": false,
      "cases": [
        {"id": "loja-01", "split": "dev", "action": "click",
         "query": "adicionar os fones de ouvido ao carrinho",
         "expected": ".card:nth-of-type(2) .add"}
      ]
    }

- `action`: nome da ação do Executor (click, fill, check, select, extract_text...).
- `expected`: seletor CSS (ou do Playwright, como `:has-text()`) do elemento certo.
  Se mais de um elemento for aceitável, o seletor pode casar com vários.
- `split`: `dev` para ajustar pesos e sinônimos; `test` só para medir.
- `synonyms` (opcional, no nível do site): vocabulário específico, passado ao Resolver.

## Regra de ouro

Ajuste pesos, sinônimos e heurísticas olhando **apenas** o `dev`.
O número que vai para o artigo é o do `test`. Se você melhorar o código
olhando os casos de teste, o resultado deixa de medir generalização.

## Resultados por caso (`outcome`)

| valor | significado |
|---|---|
| `acerto` | o Executor decidiu e escolheu o elemento certo |
| `erro_silencioso` | o Executor decidiu, mas escolheu o elemento **errado** (o pior caso) |
| `recusa_evitavel` | o certo estava em 1º, mas o Executor recusou (limiar conservador) |
| `recusa_correta` | o Executor recusou e o 1º estava errado (evitou um erro) |
| `falha_percepcao` | o elemento certo nem foi indexado pelo `index_script.js` |

## Holdout (conjunto de teste fechado)

Os arquivos `cases/holdout_*.json` (split `test`) formam o conjunto fechado,
criado em 25/09/2026 **antes** das correções de verbo conflitante e da
recalibração dos limiares. Os casos do antigo split `test` viraram `dev`
(campo `split_original: "test"`), porque já tinham sido consultados.

Regras:

1. `python -m eval.run` nunca roda o holdout. Só `--final` roda, e o
   resultado sai com o sufixo `_FINAL` no nome do arquivo.
2. Rode `--final` **uma vez**, quando o desenvolvimento do Resolver estiver
   encerrado. Os números do artigo vêm dessa rodada.
3. Se algo for alterado depois de olhar o holdout, registre isso no artigo.
4. `--check` pode ser usado a qualquer momento: só confere se os seletores
   esperados existem, sem calcular scores.

### Consultas de colegas (recomendado)

As consultas do holdout foram escritas pelo mesmo autor das heurísticas
(viés de autoria). Para reduzir esse viés, peça a 2 ou 3 pessoas que:

1. abram cada página de `fixtures/holdout_*.html` no navegador;
2. escrevam, para 8 a 10 elementos, como pediriam aquela ação a um
   assistente ("quero cancelar o pedido do dia 3 de novembro");
3. sem ver o código nem os casos existentes.

Adicione essas consultas como novos casos `split: "test"`, com ids
`h-<pagina>-cNN`, e reporte os dois grupos separadamente no artigo.


## Conjunto fechado de tarefas do planejador

As tarefas de `plans/tasks.json` foram usadas para ajustar o prompt do planejador, então os
números delas são de desenvolvimento. Os números finais vêm de `plans/holdout_tasks.json`
(split `test`), que só roda com `python -m eval.plan_run --final`, uma única vez.

Como montar o conjunto:

1. **Pedidos escritos por outras pessoas.** Peça a 2 ou 3 colegas que abram as páginas de
   `fixtures/` no navegador e escrevam, para cada uma, 5 a 8 pedidos como fariam a um
   assistente ("quero reservar a sala Amazonas para amanhã às 10h"), sem ver o código nem as
   tarefas existentes. A meta é chegar a 30 ou 40 pedidos.
2. **Metade em páginas novas, metade nas antigas.** Use as páginas `holdout_*.html` (nunca
   vistas pelo planejador) e as de desenvolvimento, com pedidos novos. Assim, o artigo separa
   a generalização para pedidos novos da generalização para páginas novas. As `holdout_*`
   também são o conjunto fechado do Resolver, e os dois `--final` rodam no fim.
3. **Transformar cada pedido em tarefa**, no formato de `tasks.json`: `checks` (o estado final
   esperado), `allowed` (os elementos que a tarefa pode acionar), `reference` (o plano certo,
   escrito à mão) e `"split": "test"`. Pedidos ambíguos ou impossíveis na página podem ficar,
   com o `checks` descrevendo o comportamento certo (por exemplo, nenhum clique).
4. **Conferir sem rodar nada:** `python -m eval.plan_run --check` valida campos, páginas,
   seletores e verificações, sem chamar modelos nem a heurística.
5. **Não rodar os modelos nessas tarefas nem ajustar o prompt olhando para elas** até a
   rodada final. Se algo mudar depois de olhar, registre no artigo.
