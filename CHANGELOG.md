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
- Licença PolyForm Strict 1.0.0 (`LICENSE`): uso não comercial permitido, sem modificação nem
  redistribuição; direitos autorais do autor. Seção "Uso responsável" no README.

### Alterado
- Elementos aninhados viram um candidato só quando um contém o outro e apenas um deles é
  interativo (ex.: o link de um produto e o nome dentro dele); fica o interativo, com o maior
  score dos dois. O script de percepção passou a informar `parentId` e `interactive`.
- A memória das escolhas guarda no máximo 500 escolhas por arquivo; ao passar disso, descarta a
  usada há mais tempo.

## [0.2.1] - 2026-09-26

Correções encontradas em testes em sites reais (LinkedIn e CoinMarketCap), reproduzidas em
páginas locais. No conjunto de desenvolvimento do Resolver (52 casos locais), o recall@1 foi de
80,8% para 82,7% e o erro silencioso caiu de 3,8% para 1,9%.

### Corrigido
- Pop-ups sumiam do resumo da página enviado ao planejador: em páginas grandes, o limite de 80
  elementos era preenchido pelo cabeçalho, e os pop-ups ficam no fim do código. O resumo agora
  vem em ordem de relevância (pop-up aberto, marcado com `[pop-up]`; visível na tela; resto), e
  elementos cobertos pelo pop-up ficam de fora.
- Um clique que abria um pop-up não gerava replanejamento (só a mudança de URL gerava). O
  agente agora replaneja quando um pop-up, diálogo ou menu abre ou fecha.
- O Resolver aceitava elementos que não podiam receber a ação (ex.: preencher um botão). Agora
  há um filtro por ação: preencher só considera campos de texto, selecionar só listas nativas,
  marcar só caixas, opções e chaves.
- Buscas sem botão (só com Enter) travavam: um clique de pesquisar/buscar que não encontra um
  botão, logo depois de preencher um campo, vira Enter nesse campo. O prompt também orienta a
  usar `press Enter` quando não há botão de busca.
- Laço de repetição: o mesmo passo repetido logo depois de um replanejamento é barrado, com um
  aviso ao planejador, e nenhum passo roda mais de 3 vezes. A conferência do fim roda no máximo
  2 vezes por execução.
- Elementos escolhidos pelo clique do usuário eram guardados na memória só com o texto. Agora a
  página é reindexada e a assinatura completa é guardada; e um elemento com texto idêntico e
  único na página é reencontrado mesmo que o contexto tenha mudado.
- Ctrl+C mostrava o erro completo: agora os comandos encerram com uma mensagem curta e fecham
  o navegador.
- A conferência do fim que só propõe passos já feitos conta como objetivo atingido (antes, a
  detecção de laço transformava isso em falha).
- Em páginas grandes, o elemento que o pedido precisa podia ficar fora do resumo mesmo sem
  pop-up (ex.: a lupa depois de 90 links). O resumo agora é guiado pelo pedido: elementos com
  palavras em comum com ele entram logo depois dos pop-ups.
- Digitar num campo de busca abria a lista de sugestões e gerava um replanejamento, que levava
  o modelo a clicar nas sugestões em vez de pesquisar. Preencher não gera mais replanejamento
  por pop-up.
- Ao clicar, o valor já digitado num campo fazia o campo competir com os itens que tinham
  aquele texto (ex.: a sugestão de pesquisa). Fora do preenchimento, o valor não identifica
  mais o campo.

### Alterado
- Barreira para ações destrutivas não pedidas: um passo que fecha, exclui, remove, oculta ou
  cancela algo que o pedido não mencionou não é executado, e o planejador é avisado. Fechar um
  pop-up não conta.
- Nome idêntico: um elemento cujo texto é exatamente o que o pedido nomeia (ignorando palavras
  de tipo como "Opção" e "Botão") ganha um bônus pequeno sobre os que só contêm a frase.
  Não vale na extração, que já tem a regra própria de texto exato.
- O prompt orienta a clicar no elemento que revela o que falta (lupa, "Search", menu) e a só
  responder que o pedido não pode ser feito quando nada na página levaria a ele.
- Pedido sem verbo, que só nomeia um item: elementos que anunciam uma ação destrutiva ou de
  descarte (fechar, excluir, remover, ocultar, dispensar, cancelar, limpar) perdem pontos.
- O prompt pede para não fechar, ocultar nem dispensar itens que o pedido não mencionou.
- A rede de segurança de `select` tenta marcar a opção quando a lista não resolve o passo.
- `eval/plan_run.py --check`: elementos permitidos que só surgem depois (ex.: sugestões de
  pesquisa) geram um aviso, não um problema; o plano de referência, no modo `--agente`,
  devolve os passos que faltam a cada replanejamento.

### Adicionado
- Três tarefas de desenvolvimento que reproduzem os testes reais: busca num pop-up
  (`busca_popup.html`), busca só com Enter e sugestões (`busca_enter.html`) e lista de vagas
  com "Salvar" e "Fechar vaga" (`vagas.html`).

## [0.2.0] - 2026-09-26

Agente completo: o sistema recebe um pedido em texto e um link, gera o plano com um LLM,
executa, replaneja quando precisa e confere se o objetivo foi atingido. Nas 12 tarefas de
desenvolvimento, pelo loop do agente, os dois modelos locais (Qwen 3.5 com 4B e 9B)
cumpriram todas; 10 e 9 delas, respectivamente, sem nenhum passo não pedido.

### Adicionado
- Loop do agente (`app/agent`): plano inicial, execução passo a passo, replanejamento quando
  a página muda ou um passo falha (com o motivo, inclusive elemento coberto por modal),
  conferência do fim ("objetivo atingido" quando nada falta), cancelamento com relato depois
  de 3 falhas e limite de passos. Registra chamadas ao modelo, replanejamentos, falhas,
  intervenções do usuário, tokens e tempo.
- Comando `python -m app.agent --perfil <nome> --url <link> "<pedido>"`, com navegador
  visível, desempate no terminal, memória das escolhas e perfil persistente opcional.
- O planejador aceita o histórico da execução para replanejar só o que falta.
- `eval/plan_run.py --agente`: as tarefas executadas pelo loop do agente completo.
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

- Métrica de passos não pedidos em `eval/plan_run.py`: cada tarefa lista os elementos
  permitidos (`allowed`), e qualquer outro elemento acionado (clique, digitação ou escolha)
  conta; a tabela mostra também as tarefas "limpas" (cumpridas sem passo a mais).
- Conjunto fechado de tarefas do planejador (`eval/plans/holdout_tasks.json`, vazio por
  enquanto), que só roda com `--final`, e `--check` para conferir as tarefas sem chamar modelos.
- Limpeza das descrições dos passos antes da execução: tira rótulos de tipo copiados do
  resumo da página ("Campo de texto", "Caixa de marcação", "Lista de opções") e aspas.
- `select` em botão de opção ou caixa de marcação é refeito como `check`.

### Alterado
- Prompt do planejador: qual ação usar para cada tipo de elemento, descrição sem o tipo,
  passo que conclui o pedido, nada de passos não pedidos, e login sem senha (o usuário
  digita a senha e clica em entrar).
- Tarefa `p-log-01` ajustada ao desenho do sistema: preencher o usuário e parar antes de
  entrar, sem digitar a senha.
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

[Não lançado]: https://github.com/LucasDantas2701/smart-rpa/compare/v0.2.1...develop
[0.2.1]: https://github.com/LucasDantas2701/smart-rpa/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/LucasDantas2701/smart-rpa/compare/v0.1.0...v0.2.0
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
