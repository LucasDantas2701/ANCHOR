# ANCHOR

**A**daptive **N**atural-language **C**ontrol with **H**uman **O**versight and **R**ecovery

*[Read in English](README.md)*

O agente de automação web ANCHOR faz **RPA com IA** que roda **no seu computador**: você descreve
a tarefa em português, um **LLM local** (pelo Ollama) planeja os passos, o Playwright os executa no
navegador, e você continua no controle.

## O que ele faz

A automação web tradicional depende de seletores fixos, escritos por um programador, e quebra
quando a página muda. Com o ANCHOR, quem conhece a tarefa escreve o pedido como pediria a um colega:

```text
Cadastre a colaboradora Maria Silva, CPF 123.456.789-00, departamento de TI, contrato PJ. Aceite os termos e salve o cadastro.
```

e ele planeja, executa e confere cada passo. Uma tarefa aprendida pode ser salva e repetida sem o
modelo, inclusive uma vez por linha de uma planilha.

## Por que o ANCHOR

* **Roda inteiro no seu computador:** os planos vêm de um modelo pequeno (Qwen 3.5, de 4B ou 9B)
  rodando no Ollama; nenhuma página, pedido ou senha sai da sua máquina.
* **Você continua no controle:** ele pergunta antes de qualquer ação sensível (salvar, enviar,
  pagar, excluir, agir na sua conta), bloqueia o que o pedido não pediu e para em vez de adivinhar.
  A IA nunca vê uma senha: o login é feito por você, na tela, ou com um login que você salvou para
  aquele site exato (a senha fica no Gerenciador de Credenciais do Windows).
* **Se recupera sozinho:** quando a página muda, ele acha o elemento de novo, confere cada passo e
  guarda a correção para a próxima vez.
* **É medido:** suítes de desenvolvimento, páginas com injeção de instruções e um benchmark de
  resiliência contra um script tradicional e um LLM no controle.
* **É código aberto**, sob a licença Apache 2.0.

## Como começar

1. Instale o [Ollama](https://ollama.com/download), que roda a IA no seu computador.
2. Baixe o [**ANCHOR-Setup.exe**](https://github.com/LucasDantas2701/ANCHOR/releases/latest/download/ANCHOR-Setup.exe) (sempre a versão mais recente) e execute. Ele instala só para o seu usuário (sem senha de administrador).
3. Abra o ANCHOR pelo menu Iniciar. Na primeira vez, ele baixa o navegador que controla e pelo menos
   um modelo de IA, com um botão para cada.

> [!NOTE]
> Enquanto o instalador não tiver assinatura digital, o Windows pode avisar que ele é de um **editor
> desconhecido**: clique em **Mais informações** e depois em **Executar assim mesmo**. O instalador é
> montado pelo GitHub a partir do código deste repositório.

O ANCHOR abre numa janela própria, com um guia curto na primeira vez. A interface começa no idioma do
computador (português ou inglês) e muda em **Configurações → Idioma**; os pedidos podem ser em
português. Para atualizar, baixe e execute o `ANCHOR-Setup.exe` de novo: as suas automações,
agendamentos e logins são mantidos.

Precisa de Windows 10 ou 11, e uma placa de vídeo com 4 GB já basta (tudo aqui foi medido numa GTX
1050 Ti). O passo a passo completo, como rodar a partir do código, a referência de comandos e a
avaliação estão no [README em inglês](README.md).

## Licença e citação

Apache 2.0 (veja [LICENSE](LICENSE)). Para citar o ANCHOR, use o [CITATION.cff](CITATION.cff).
