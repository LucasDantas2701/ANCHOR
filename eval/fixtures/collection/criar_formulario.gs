/**
 * Cria o Google Forms da coleta de pedidos humanos (artigo do ANCHOR).
 *
 * COMO USAR
 * 1. Envie a pasta "prints" (9 imagens .png) para o seu Google Drive.
 * 2. Abra a pasta no Drive e copie o ID dela: é o trecho da URL depois de /folders/.
 * 3. Em https://script.google.com, crie um projeto novo, apague o conteúdo e cole este arquivo.
 * 4. Cole o ID da pasta em PASTA_PRINTS_ID, logo abaixo.
 * 5. Selecione a função criarFormulario e clique em Executar. Autorize o acesso ao Forms e ao Drive.
 * 6. Em "Registro de execução" aparecem dois links: o de edição e o de resposta.
 * 7. Abra o link de edição e confira (ver o fim deste arquivo).
 */

const PASTA_PRINTS_ID = 'COLE_AQUI_O_ID_DA_PASTA';
const BASE = 'https://lucasdantas2701.github.io/web-pages-study/';

// Páginas da coleta (versão em português, eval/fixtures/collection/).
// Distribuição: 2 pedidos nas 4 páginas novas e na loja, 1 nas demais (14 por pessoa).
// O código Pxx no título das perguntas identifica a página na planilha de respostas;
// "origem" é a página do pacote sintético de que cada uma veio.
const PAGINAS = [
  { cod: 'P01', arq: 'reservas', nome: 'Reserva de salas',        origem: 'holdout_booking',  pedidos: ['Pedido 1', 'Pedido 2'] },
  { cod: 'P02', arq: 'suporte',  nome: 'Central de chamados',     origem: 'holdout_helpdesk', pedidos: ['Pedido 1', 'Pedido 2'] },
  { cod: 'P03', arq: 'blog',     nome: 'Publicações (CMS)',       origem: 'holdout_blog',     pedidos: ['Pedido 1', 'Pedido 2'] },
  { cod: 'P04', arq: 'rh',       nome: 'PeopleHub',               origem: 'holdout_hr',       pedidos: ['Pedido 1', 'Pedido 2'] },
  { cod: 'P05', arq: 'cadastro', nome: 'Cadastro de colaborador', origem: 'registration',     pedidos: ['Pedido'] },
  { cod: 'P06', arq: 'usuarios', nome: 'Usuários',                origem: 'users',            pedidos: ['Pedido'] },
  { cod: 'P07', arq: 'pedidos',  nome: 'Meus pedidos',            origem: 'orders',           pedidos: ['Pedido'] },
  { cod: 'P08', arq: 'vagas',    nome: 'Vagas',                   origem: 'jobs',             pedidos: ['Pedido'] },
  { cod: 'P09', arq: 'loja',     nome: 'TechStore',               origem: 'store',            pedidos: ['Pedido 1', 'Pedido 2'] },
];

const TEXTO_ABERTURA =
  'Obrigado por ajudar!\n\n' +
  'Estou testando um assistente que faz tarefas em sites no lugar da pessoa. Em vez de clicar e ' +
  'preencher tudo sozinho, você escreve o que quer, como se mandasse uma mensagem para alguém ' +
  '(por exemplo, "marca uma consulta com o dentista para sexta de manhã"), e o assistente faz isso no site.\n\n' +
  'Para avaliar esse assistente, preciso de pedidos escritos por pessoas, do jeito que elas ' +
  'pediriam de verdade. Você vai ver algumas páginas de sites simulados e escrever, para cada uma, ' +
  'o que pediria ao assistente fazer nela. Leva uns 15 minutos.\n\n' +
  'Se não souber o que pedir, imagine uma situação: por exemplo, que você trabalha na empresa ' +
  'dona daquele sistema, ou que é cliente do site, e precisa resolver alguma coisa nele. Escreva o ' +
  'pedido que você faria nessa situação.\n\n' +
  'Antes de começar:\n' +
  '• A participação é voluntária. Você pode parar a qualquer momento antes de enviar.\n' +
  '• Os pedidos e as demais respostas deste formulário poderão ser publicados em um artigo ' +
  'científico e em um ' +
  'repositório público na internet, sob licença aberta.\n' +
  '• Este formulário não coleta nome, e-mail nem qualquer dado que identifique você. Por isso, ' +
  'depois de enviada, não há como localizar ou retirar a sua resposta.\n' +
  '• Não escreva dados pessoais reais nos pedidos, nem seus nem de outras pessoas. Quando ' +
  'precisar de um nome, e-mail ou data, invente.';

const TEXTO_INSTRUCOES =
  'Nas próximas 9 seções aparece uma página de um site simulado: uma imagem dela e um link para ' +
  'abri-la no navegador. As páginas são simuladas (nada é enviado para lugar nenhum), então pode ' +
  'clicar à vontade para entender o que cada uma faz. Algumas opções só aparecem clicando, como ' +
  'listas e botões; por isso vale abrir o link.\n\n' +
  'Para cada página, escreva pedidos para o assistente. Cada pedido é uma ordem ou uma pergunta ' +
  'para o assistente, que vai fazer isso por você na página. Não escreva o texto que você ' +
  'digitaria no site: escreva o que você pediria para alguém fazer lá.\n\n' +
  'Exemplo, num site de pizzaria (que não está entre as páginas):\n' +
  '  Assim não: "calabresa grande"  (isso é o que se digita no site)\n' +
  '  Assim sim: "pede uma pizza de calabresa grande para entregar às 20h"\n' +
  '  Também vale: "quanto custa a entrega no meu bairro?"\n\n' +
  'O QUE VALE\n' +
  '• Pedidos curtos ou longos, diretos ou vagos, formais ou informais: do jeito que vier.\n' +
  '• Pedidos com mais de uma coisa ("cadastra a Ana no RH e salva") também valem.\n' +
  '• Pedidos ambíguos, ou que a página não permite fazer, também servem: saber recusar ou ' +
  'perguntar também é avaliado.\n' +
  '• Use os nomes, valores e itens que aparecem na página, ou invente dados quando fizer sentido.\n' +
  '• Se faltar ideia, invente um cenário (você é funcionário, cliente, gerente...) e peça o que ' +
  'faria sentido nele.\n\n' +
  'O QUE NÃO FAZER\n' +
  '• Não abra o código das páginas (nem o "inspecionar" do navegador) e não procure o site ou o ' +
  'projeto na internet: o objetivo é ter pedidos de quem só vê a página, como um usuário comum.\n' +
  '• Não combine os pedidos com outras pessoas que também estão ajudando.';

function criarFormulario() {
  const pasta = DriveApp.getFolderById(PASTA_PRINTS_ID);
  const form = FormApp.create('Pedidos para um assistente de automação web');

  // Configurações: anônimo, sem login, sem edição depois de enviar.
  form.setDescription(TEXTO_ABERTURA);
  tentar(() => form.setCollectEmail(false));
  tentar(() => form.setRequireLogin(false));
  tentar(() => form.setLimitOneResponsePerUser(false));
  tentar(() => form.setAllowResponseEdits(false));
  tentar(() => form.setShowLinkToRespondAgain(false));
  tentar(() => form.setPublishingSummary(false));
  tentar(() => form.setProgressBar(true));
  form.setConfirmationMessage(
    'Obrigado! Sua resposta foi registrada. Por favor, não comente os seus pedidos com outras ' +
    'pessoas que também vão responder.');

  // Seção 1: consentimento. Quem não concorda vai direto para o fim.
  const cons = form.addMultipleChoiceItem();
  cons.setTitle('Você concorda em participar nessas condições?')
    .setChoices([
      cons.createChoice('Li e concordo', FormApp.PageNavigationType.CONTINUE),
      cons.createChoice('Não concordo', FormApp.PageNavigationType.SUBMIT),
    ])
    .setRequired(true);

  // Seção 2: instruções e perfil.
  form.addPageBreakItem().setTitle('Como funciona').setHelpText(TEXTO_INSTRUCOES);
  form.addMultipleChoiceItem()
    .setTitle('Você trabalha com programação ou TI?')
    .setChoiceValues(['Sim', 'Não'])
    .setRequired(true);

  // Seções 3 a 11: uma por página.
  PAGINAS.forEach((p, i) => {
    const url = BASE + p.arq + '.html';
    form.addPageBreakItem()
      .setTitle(`Página ${i + 1} de ${PAGINAS.length}: ${p.nome}`)
      .setHelpText(`Abra a página: ${url}\n\nAbra o link antes de escrever: a imagem não mostra tudo o que a página tem.`);

    const arquivos = pasta.getFilesByName(p.arq + '.png');
    if (!arquivos.hasNext()) throw new Error('Imagem não encontrada na pasta: ' + p.arq + '.png');
    form.addImageItem()
      .setImage(arquivos.next().getBlob())
      .setTitle(p.nome);

    form.addMultipleChoiceItem()
      .setTitle(`${p.cod} · Você abriu o link desta página?`)
      .setChoiceValues(['Sim', 'Não'])
      .setRequired(true);

    p.pedidos.forEach(rotulo => {
      form.addParagraphTextItem()
        .setTitle(`${p.cod} · ${rotulo}`)
        .setHelpText('O que você pediria para o assistente fazer (ou responder) nesta página?')
        .setRequired(true);
    });
  });

  tentar(() => form.setPublished(true));
  Logger.log('Link de edição: ' + form.getEditUrl());
  Logger.log('Link para responder: ' + form.getPublishedUrl());
}

function tentar(fn) {
  try { fn(); } catch (e) { Logger.log('Aviso (confira à mão): ' + e.message); }
}

/*
 * CONFERIR À MÃO DEPOIS DE CRIAR (Configurações do formulário)
 * - Respostas > Coletar endereços de e-mail: "Não coletar".
 * - "Limitar a 1 resposta" desligado (essa opção exige login).
 * - "Permitir edição após o envio" desligado.
 * - O formulário está publicado e aceitando respostas.
 * - Se aparecer algum "Aviso" no registro de execução, ajuste esse item manualmente.
 *
 * Responda uma vez para testar (com "Não concordo" e depois completo) e apague essas
 * respostas de teste antes de divulgar.
 */
