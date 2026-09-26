# Smart RPA

> Automação inteligente de processos web utilizando Playwright, agentes de IA e resolução adaptativa de elementos.

**Smart RPA** é um projeto experimental voltado para a construção de uma abordagem mais inteligente e flexível para **RPA (Robotic Process Automation)**.

A proposta é combinar automação de navegadores, resolução semântica de elementos e agentes de IA para criar automações capazes de **interpretar tarefas, executar ações e se adaptar a mudanças nas interfaces web**.

## Visão geral

Automações tradicionais de navegadores normalmente dependem de seletores definidos manualmente:

```python
page.locator('[data-test="add-to-cart"]').click()
```

Isso funciona enquanto a estrutura da página permanece estável. Pequenas alterações na interface podem fazer com que a automação deixe de funcionar.

O Smart RPA busca criar uma camada de abstração entre o agente e o navegador:

```text
Usuário
   │
   ▼
Agente de IA
   │
   ▼
Planejador / Orquestrador
   │
   ▼
Camada de Ações
   │
   ▼
Resolvedor de Elementos
   │
   ▼
Motor do Navegador
   │
   ▼
Playwright
   │
   ▼
Navegador
```

A ideia é que o agente descreva **o que precisa ser feito**, enquanto o sistema determina **como executar a ação**.

Por exemplo:

```text
"Adicione a mochila ao carrinho"
             │
             ▼
         Agente de IA
             │
             ▼
          ação: click
             │
             ▼
    Resolvedor de Elementos
             │
             ▼
Encontra o botão correspondente
             │
             ▼
          Playwright
```

## Status do projeto

🚧 **Versão 0.1: motor de execução.** O sistema já executa passos descritos em
linguagem natural numa página real, pergunta ao usuário quando não tem certeza
e aprende com as respostas. O **planejador** (LLM que transforma o pedido do
usuário em passos) e o **loop do agente** ainda não existem: por enquanto, os
passos são escritos à mão.

### Implementado

* [x] **Percepção da página** (`index_script.js`): indexa só os elementos interativos
  (links, botões, campos, papéis ARIA e áreas clicáveis por `cursor: pointer`), com
  nome acessível, pistas visuais de ícones, estado, contexto do card e geometria.
  Entra em shadow DOM aberto.
* [x] **Resolvedor de elementos** heurístico: normalização de texto (acentos, plurais,
  expressões compostas), sinônimos PT→EN, vocabulário por site e scoring por ação.
* [x] **Executor de ações**: click, hover, check, uncheck, press, fill, select e extrações,
  com validação por score mínimo e margem relativa de ambiguidade.
* [x] **Desempate pelo usuário**: quando a heurística não tem certeza, os candidatos são
  numerados na página e o usuário escolhe no terminal, ou clica direto no elemento.
* [x] **Memória das escolhas**: o que o usuário escolheu é reaproveitado nas próximas
  execuções, com expiração automática e comando de revisão.
* [x] **Avaliação reproduzível**: casos de desenvolvimento e um conjunto de teste fechado
  (holdout), com métricas atreladas ao commit.
* [x] Perfis persistentes do navegador e detecção de login.
* [x] **Planejador** (em desenvolvimento, versão 0.2.0): um LLM transforma o pedido
  do usuário em passos, usando os nomes dos elementos da página. Funciona com a API da
  OpenAI e com modelos locais do Ollama.

### Ainda não implementado

* [ ] Loop do agente, com replanejamento quando a página não bate com o plano.
* [ ] Automações salvas, com dados próprios.
* [ ] Confirmação humana antes de ações sensíveis.
* [ ] Frontend (hoje a interação é pelo terminal).

## Como funciona hoje

```text
Passo em linguagem natural ("adicionar a mochila ao carrinho")
        │
        ▼
Memória: o usuário já escolheu este elemento antes? ── sim ──► executa
        │ não
        ▼
Percepção: indexa os elementos interativos da página (index_script.js)
        │
        ▼
Resolvedor: ranqueia os candidatos pela descrição
        │
        ▼
Validação: score mínimo e margem para o 2º colocado
        │                              │
     confiante                   ambíguo / não encontrado
        │                              │
        │                              ▼
        │                 Usuário escolhe (número ou clique na página)
        │                              │
        │                              ▼
        │                 Escolha guardada na memória
        ▼                              ▼
                Playwright executa a ação
```

## Como rodar

Requisitos: Python 3.10 ou mais recente.

```bash
python -m venv venv
venv\Scripts\activate            # Windows  (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
playwright install chromium
```

### Exemplo no SauceDemo

```bash
python -m app.main
```

Na primeira execução, faça o login na janela do navegador
(`standard_user` / `secret_sauce`). A sessão fica no perfil persistente.

### Demonstração do desempate e da memória

```bash
python -m examples.desempate
```

Rode duas vezes: na primeira, o assistente pergunta; na segunda, usa as escolhas memorizadas.

### Revisar o que o assistente aprendeu

```bash
python -m app.engine.memory memory/demo.json listar
python -m app.engine.memory memory/demo.json esquecer 2
python -m app.engine.memory memory/demo.json limpar
```

### Testes

```bash
pytest tests/engine -v
```

Os testes em `tests/real_sites/` (LinkedIn) ficam desativados por padrão, porque os termos
de uso do site proíbem automação.

### Padrão dos imports

Os imports seguem a PEP 8, em três grupos separados por uma linha em branco:
biblioteca padrão, bibliotecas de terceiros e módulos do projeto. Antes de commitar:

```bash
isort --check-only app eval tests examples   # só verifica
isort app eval tests examples                # corrige
```

### Planejador (LLM)

Os modelos ficam em `llm_profiles.json`, um perfil por modelo. O arquivo nunca guarda
chaves: `api_key_env` é o nome da variável de ambiente onde a chave está.

**Modelos locais (Ollama, grátis):** instale o [Ollama](https://ollama.com), baixe os modelos
e coloque os nomes exatos (veja com `ollama list`) nos perfis `ollama-pequeno` e `ollama-medio`:

```bash
ollama pull qwen3.5:4b
ollama pull qwen3.5:9b
```

Nos perfis do Ollama, use a API nativa (`"api": "ollama"`). Ela permite desligar o raciocínio
dos modelos "thinking" (`"think": false`), que multiplica o tempo de cada plano, e reduzir o
contexto (`"options": {"num_ctx": 4096}`), o que ajuda o modelo a caber numa placa de vídeo
pequena:

```json
{
  "name": "ollama-pequeno",
  "model": "qwen3.5:4b",
  "api": "ollama",
  "base_url": "http://localhost:11434",
  "think": false,
  "options": {"num_ctx": 4096},
  "api_key_env": null
}
```

Para ver se o modelo está na placa de vídeo ou no processador: `ollama ps` (coluna `PROCESSOR`).

**OpenAI (pago):** crie uma chave na plataforma de desenvolvedores da OpenAI (a assinatura do
ChatGPT não dá acesso à API), guarde-a numa variável de ambiente e preencha o modelo no
perfil `openai`:

```bash
setx OPENAI_API_KEY "sua-chave"        # Windows; abra um terminal novo depois
```

Gerar um plano, e executá-lo no navegador:

```bash
python -m app.planner --perfil ollama-pequeno --url eval/fixtures/cadastro.html "cadastre a Maria Silva no departamento de TI"
python -m app.planner --perfil ollama-pequeno --url eval/fixtures/cadastro.html "cadastre a Maria Silva no departamento de TI" --executar
```

Comparar os modelos em tarefas completas (pedido → plano → execução → estado final):

```bash
python -m eval.plan_run --referencia                                    # planos escritos à mão (teto)
python -m eval.plan_run --perfis ollama-pequeno ollama-medio openai -v  # os três modelos
```

### Avaliação

```bash
python -m eval.run -v            # casos de desenvolvimento (inclui o SauceDemo real)
python -m eval.run --offline     # só as páginas locais
python -m eval.run --sweep       # testa combinações de limiares
python -m eval.run --check       # confere os seletores esperados, sem calcular scores
```

O conjunto de teste fechado (holdout) só roda com `--final`, uma única vez, no fim do
desenvolvimento. Detalhes em [`eval/README.md`](eval/README.md).

## Resultados atuais

Conjunto de desenvolvimento, 60 casos em 7 páginas (6 locais e o SauceDemo), commit `0de5a8b`:

| Métrica | Valor |
|---|---|
| Elemento certo em 1º (recall@1) | 83,3% |
| Elemento certo entre os 5 primeiros (recall@5) | 90,0% |
| Executor decide e acerta | 76,7% |
| Executor decide e erra (erro silencioso) | 3,3% |
| Executor recusa e pergunta ao usuário | 20,0% |

Estes números medem a evolução durante o desenvolvimento, não a generalização: os casos foram
consultados enquanto o código era ajustado. A generalização será medida no holdout.

## Estrutura

```text
smart-rpa/
├── app/
│   ├── main.py                    # exemplo de ponta a ponta no SauceDemo
│   ├── browser/                   # perfis persistentes, sessão e login
│   ├── planner/                   # LLM: pedido → passos (perfis, validação, execução)
│   ├── engine/
│   │   ├── element_resolver/      # percepção (index_script.js) + ranqueamento
│   │   ├── action_executor/       # validação e execução das ações
│   │   ├── disambiguation/        # desempate pelo usuário (terminal; contrato para o frontend)
│   │   └── memory/                # memória das escolhas + comando de revisão
│   ├── actions/                   # ações de baixo nível por seletor (legado)
│   └── automation/saucedemo.py    # exemplo LEGADO com seletores fixos (o "antes")
├── eval/                          # avaliação: páginas, casos, resultados, holdout e tarefas (plans/)
├── examples/                      # demonstrações
├── tests/
│   ├── engine/                    # testes do motor
│   └── real_sites/                # exploratórios, desativados por padrão
├── profiles/                      # perfis do navegador (fora do Git)
├── memory/                        # escolhas memorizadas (fora do Git)
└── llm_profiles.json              # perfis dos modelos de LLM (sem chaves)
```

## Sessões persistentes

O Smart RPA utiliza perfis persistentes do Playwright para manter sessões do navegador localmente.

Isso permite reutilizar uma sessão autenticada sem que credenciais precisem ser enviadas para o agente de IA.

O fluxo esperado é:

```text
Primeira execução
       │
       ▼
Abre o navegador
       │
       ▼
Usuário realiza o login
       │
       ▼
Sessão armazenada localmente
       │
       ▼
Próximas execuções
       │
       ▼
Reutilização da sessão
```

Os perfis do navegador são ignorados pelo Git e não fazem parte do repositório.

## Limitações conhecidas

* O casamento de texto é por palavras, com um dicionário de sinônimos; não há semântica real.
  Extração de dados ("o preço do produto X") é o ponto mais fraco.
* Iframes e shadow DOM fechado não são lidos.
* Quando a heurística erra com confiança (erro silencioso), o usuário não é consultado.
* Execuções sem ninguém por perto param quando há ambiguidade, até a memória aprender.

## Contexto

Projeto de TCC na Faculdade Matias Machline (Manaus-AM), de Lucas dos Santos Dantas.
