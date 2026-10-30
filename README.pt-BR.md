# ANCHOR

**A**daptive **N**atural-language **C**ontrol with **H**uman **O**versight and **R**ecovery

*[Read in English](README.md)*

O agente de automação web ANCHOR faz **RPA com IA** que roda **no seu computador**: você descreve
a tarefa em português, um **LLM local** (pelo Ollama) planeja os passos, o Playwright os executa no
navegador, e você continua no controle.

## O que ele faz

A automação web tradicional depende de seletores fixos, escritos por um programador, e quebra
quando a página muda. Com o ANCHOR, quem conhece a tarefa escreve o pedido como pediria a um colega,
e ele planeja, executa e confere cada passo. Uma tarefa aprendida pode ser salva e repetida sem o
modelo, inclusive uma vez por linha de uma planilha.

## Por que o ANCHOR

* **Roda inteiro no seu computador:** os planos vêm de um modelo pequeno (Qwen 3.5, de 4B ou 9B)
  rodando no Ollama; nenhuma página, pedido ou senha sai da sua máquina.
* **Você continua no controle:** ele pergunta antes de qualquer ação sensível (salvar, enviar,
  pagar, excluir, baixar ou enviar arquivos), bloqueia o que o pedido não pediu, deixa os logins com
  você e para em vez de adivinhar.
* **Se recupera sozinho:** quando a página muda, ele acha o elemento de novo, confere cada passo e
  guarda a correção para a próxima vez.
* **É medido:** suítes de desenvolvimento, páginas com injeção de instruções e um benchmark de
  resiliência contra um script tradicional e um LLM no controle.
* **É código aberto**, sob a licença Apache 2.0.

## Como começar

Você precisa de Python 3.10 ou mais novo e do [Ollama](https://ollama.com). Depois:

```sh
git clone https://github.com/LucasDantas2701/ANCHOR.git
cd ANCHOR
python -m venv venv
venv\Scripts\activate            # Windows (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
playwright install chromium
ollama pull qwen3.5:4b
```

E um primeiro pedido, numa página de teste que vem com o repositório:

```sh
python -m anchor.agent --profile ollama-small --url eval/fixtures/registration.html "Cadastre a colaboradora Maria Silva, CPF 123.456.789-00, e-mail maria.silva@empresa.com.br, departamento de TI, contrato PJ. Aceite os termos e salve o cadastro."
```

O navegador abre, o ANCHOR planeja e executa cada passo, pergunta no terminal quando não tem certeza
(e antes de salvar, que é uma ação sensível) e, no fim, mostra o resultado. A interface gráfica chega
na versão 0.5. O passo a passo completo e a referência de comandos estão no [README em inglês](README.md).

## Licença e citação

Apache 2.0 (veja [LICENSE](LICENSE)). Para citar o ANCHOR, use o [CITATION.cff](CITATION.cff).
