# Changelog

Todas as mudanças relevantes do projeto ficam registradas aqui.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e o projeto usa [Versionamento Semântico](https://semver.org/lang/pt-BR/)
(MAJOR.MINOR.PATCH):

- **MAJOR**: mudança que quebra compatibilidade (ex.: formato da memória ou dos casos de avaliação).
- **MINOR**: funcionalidade nova, compatível com o que existe.
- **PATCH**: correção de bug, sem funcionalidade nova.

Enquanto o MAJOR for 0, o projeto está em desenvolvimento inicial, e mudanças
que quebram compatibilidade também sobem o MINOR.

## [Não lançado]

### Adicionado
- Número da versão no código (`app.__version__`), gravado também nos resultados da avaliação.
- Este changelog.
- Configuração do `isort` em `pyproject.toml`, para verificar a ordem dos imports.

- Planejador (`app/planner`): transforma o pedido do usuário em passos com um LLM,
  no formato da API da OpenAI (funciona com a OpenAI e com modelos locais do Ollama).
  Saída JSON validada contra as ações do Executor, com nova tentativa quando o plano
  é inválido, e lista dos elementos da página no pedido ao modelo. Descarta o raciocínio
  de modelos "thinking" (`<think>...</think>`) e aceita parâmetros extras por perfil.
- Perfis de modelo em `llm_profiles.json` (endereço, modelo e o nome da variável de
  ambiente com a chave; nunca a chave em si).
- Comando `python -m app.planner` para gerar e executar um plano a partir de um pedido e um link.
- Avaliação de tarefas completas (`eval/plan_run.py`, 12 tarefas em `eval/plans/tasks.json`):
  pedido → plano → execução → verificação do estado final, com tempo e tokens por modelo,
  e planos de referência escritos à mão como teto.

- API nativa do Ollama nos perfis (`"api": "ollama"`), com o raciocínio dos modelos
  "thinking" desligado (`"think": false`) e opções como `num_ctx`; mensagens claras quando
  o Ollama está fechado ou o modelo não existe.
- Progresso em tempo real no terminal (`app/planner/progress.py`): tempo de espera, e, com a
  API do Ollama, a resposta em streaming com a fase ("pensando" ou "escrevendo o plano") e os tokens.
- `eval/plan_run.py` carrega cada modelo antes das tarefas (o tempo de carregamento sai à
  parte, fora do tempo dos planos) e mostra o progresso de cada tarefa.

### Alterado
- O cliente da OpenAI não repete chamadas sozinho (`max_retries=0`): um tempo esgotado aparece na hora.
- O nome dos elementos no desempate e no resumo da página usa a pista visual quando o
  texto é curto demais (ex.: "shopping cart 2") e o `data-testid` quando não há outro nome.
- Imports padronizados (PEP 8): biblioteca padrão, terceiros e projeto, separados
  por linha em branco e em ordem alfabética.

## [0.1.0] - 2026-09-25

Primeira versão: motor de execução. Os passos ainda são escritos à mão; o
planejador com LLM e o loop do agente ficam para a 0.2.0.

### Adicionado
- Percepção da página (`index_script.js`) só com elementos interativos: links, botões,
  campos, papéis ARIA e áreas clicáveis por `cursor: pointer`, com nome acessível,
  pistas visuais de ícones, estado, contexto do card e geometria. Modo de extração
  com elementos de texto. Leitura de shadow DOM aberto.
- Normalização de texto: remoção de acentos, stemmer leve PT/EN, expressões compostas
  e sinônimos com vários valores.
- Vocabulário por site (`ElementResolver(synonyms=...)`), fora do dicionário genérico.
- Scoring com penalidade para elementos desabilitados e para verbos conflitantes
  (com grupos de verbos equivalentes).
- Desempate pelo usuário (`app/engine/disambiguation`): candidatos numerados na
  página, escolha no terminal ou clique direto no elemento. Contrato
  `Disambiguator` pronto para um frontend.
- Memória das escolhas (`app/engine/memory`): reaproveita as escolhas do usuário,
  reencontra o elemento pelo conteúdo, expira entradas que falham ou somem, e tem
  o comando de revisão `python -m app.engine.memory`.
- Avaliação reproduzível (`eval/`): 60 casos de desenvolvimento, holdout fechado de
  42 casos (só roda com `--final`), varredura de limiares e conferência de seletores.
- `app/main.py` com o motor semântico no SauceDemo e demonstração em `examples/desempate.py`.

### Alterado
- Limiares do Executor calibrados na avaliação: score mínimo 0,40 e margem de
  ambiguidade **relativa** de 4% (antes: 0,20 e margem absoluta de 0,08).
- O Resolver reindexa a página a cada consulta.
- Resultados vindos da memória informam `similarity` em vez de `score`.
- Testes do LinkedIn desativados por padrão (os termos de uso do site proíbem automação).

### Corrigido
- B1: regex de espaços no `index_script.js` (`/\\s+/` → `/\s+/`).
- B2: índice criado uma única vez, que ficava desatualizado depois de navegar.
- B3: atributos `data-er-id` antigos não eram removidos ao reindexar.
- B4: seletor `.inventory_item`, específico do SauceDemo, fixo no código genérico.
- B5: sinônimos de várias palavras nunca casavam.
- B6: margem de ambiguidade dependente da escala do score (agora relativa).
- Contexto dos elementos em listas de cards curtos, que englobava a lista inteira.
- Dupla contagem do objeto da consulta no rótulo e no contexto do elemento.

[Não lançado]: https://github.com/LucasDantas2701/smart-rpa/compare/v0.1.0...develop
[0.1.0]: https://github.com/LucasDantas2701/smart-rpa/releases/tag/v0.1.0

---

## Como lançar uma versão

1. Na `develop`, troque `__version__` em `app/__init__.py` pela versão final (sem `-dev`).
2. Neste arquivo, renomeie "Não lançado" para a versão e a data, e crie um "Não lançado" vazio acima.
3. Atualize os links de comparação no fim da lista de versões.
4. Commit: `git commit -m "vX.Y.Z"`.
5. Mergeie na `main`, crie a tag e envie:
   `git checkout main && git merge develop && git tag -a vX.Y.Z -m "..." && git push origin main --tags`
6. Volte para a `develop` e suba a versão para a próxima com `-dev` (ex.: `0.3.0-dev`).
