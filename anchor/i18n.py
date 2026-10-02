"""
User-facing messages in English (default) or Portuguese.

The language comes from, in order: set_language(), the ANCHOR_LANG
environment variable ("en" or "pt"), or English.

This covers what the *user* reads (terminal prompts, reports). What the
*model* reads (the planner prompt, the page summary) has its own language
setting, in anchor.planner, so that changing the interface language does not
change the model's behavior.
"""

from __future__ import annotations

import os

SUPPORTED = ("en", "pt")
DEFAULT_LANGUAGE = "en"

_current: str | None = None


def set_language(language: str | None) -> None:
    """Sets the interface language for this process (None goes back to the default)."""
    global _current
    if language is not None and language not in SUPPORTED:
        raise ValueError(f"unsupported language {language!r}; use one of {', '.join(SUPPORTED)}")
    _current = language


def get_language() -> str:
    if _current:
        return _current
    env = (os.environ.get("ANCHOR_LANG") or "").strip().lower()[:2]
    return env if env in SUPPORTED else DEFAULT_LANGUAGE


def t(key: str, language: str | None = None, **values) -> str:
    """The message for key, in the given language (or the current one)."""
    entry = MESSAGES[key]
    text = entry.get(language or get_language()) or entry[DEFAULT_LANGUAGE]
    return text.format(**values) if values else text


MESSAGES: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------ element kinds
    "kind.button": {"en": "Button", "pt": "Botão"},
    "kind.link": {"en": "Link", "pt": "Link"},
    "kind.textbox": {"en": "Text field", "pt": "Campo de texto"},
    "kind.searchbox": {"en": "Search field", "pt": "Campo de busca"},
    "kind.checkbox": {"en": "Checkbox", "pt": "Caixa de marcação"},
    "kind.radio": {"en": "Option", "pt": "Opção"},
    "kind.combobox": {"en": "Dropdown", "pt": "Lista de opções"},
    "kind.listbox": {"en": "Dropdown", "pt": "Lista de opções"},
    "kind.switch": {"en": "Toggle switch", "pt": "Chave liga/desliga"},
    "kind.tab": {"en": "Tab", "pt": "Aba"},
    "kind.menuitem": {"en": "Menu item", "pt": "Item de menu"},
    "kind.option": {"en": "Option", "pt": "Opção"},
    "kind.slider": {"en": "Slider", "pt": "Controle deslizante"},
    "kind.spinbutton": {"en": "Number field", "pt": "Campo numérico"},
    "kind.clickable": {"en": "Clickable area", "pt": "Área clicável"},
    "kind.other": {"en": "Element", "pt": "Elemento"},
    "element.no_text": {"en": "(no text)", "pt": "(sem texto)"},
    # ------------------------------------------------------------ disambiguation (terminal)
    "verb.click": {"en": "click", "pt": "clicar"},
    "verb.hover": {"en": "hover over", "pt": "passar o mouse"},
    "verb.check": {"en": "check", "pt": "marcar"},
    "verb.uncheck": {"en": "uncheck", "pt": "desmarcar"},
    "verb.press": {"en": "press a key on", "pt": "pressionar uma tecla em"},
    "verb.fill": {"en": "fill in", "pt": "preencher"},
    "verb.select": {"en": "choose an option in", "pt": "escolher uma opção em"},
    "verb.extract_text": {"en": "read the text of", "pt": "ler o texto de"},
    "verb.extract_attribute": {"en": "read", "pt": "ler"},
    "verb.extract_value": {"en": "read the value of", "pt": "ler o valor de"},
    "dis.where_browser": {"en": "in the browser window", "pt": "na janela do navegador"},
    "dis.where_image": {"en": "in the image", "pt": "na imagem"},
    "dis.ambiguous": {"en": 'I found more than one possible element for: "{description}"',
                      "pt": 'Encontrei mais de um elemento possível para: "{description}"'},
    "dis.numbered": {"en": "The candidates are numbered {where}:", "pt": "Os candidatos estão numerados {where}:"},
    "dis.not_found": {"en": 'I could not find where to {verb}: "{description}"',
                      "pt": 'Não encontrei onde {verb}: "{description}"'},
    "dis.point_hint": {"en": "If you can see the element, type C and click it in the browser.",
                       "pt": "Se você está vendo o elemento, digite C e clique nele no navegador."},
    "dis.number_hint": {"en": "If it is one of these (numbered {where}), type the number:",
                        "pt": "Se for um destes (numerados {where}), digite o número:"},
    "dis.near": {"en": "  (near: {near})", "pt": "  (perto de: {near})"},
    "dis.none_of_these": {"en": "If it is none of these, type C and click the right element in the browser.",
                          "pt": "Se não for nenhum destes, digite C e clique no elemento certo no navegador."},
    "dis.opt_point": {"en": "C to click it yourself in the browser", "pt": "C para clicar você mesmo no navegador"},
    "dis.opt_number": {"en": "a number from 1 to {count}", "pt": "número de 1 a {count}"},
    "dis.opt_skip": {"en": "S to skip this step", "pt": "P para pular este passo"},
    "dis.prompt": {"en": "Type {options}: ", "pt": "Digite {options}: "},
    "dis.invalid": {"en": "Answer not recognized, please try again.", "pt": "Resposta não reconhecida, tente de novo."},
    "dis.banner": {"en": "Click the element the assistant should use", "pt": "Clique no elemento que o assistente deve usar"},
    "dis.image_saved": {"en": "(image saved at {path})", "pt": "(imagem salva em {path})"},
    # ------------------------------------------------------------ choice memory (terminal)
    "mem.help": {"en": "Reviews the choice memory.", "pt": "Revisa a memória das escolhas."},
    "mem.help_file": {"en": "memory file (e.g. memory/demo.json)", "pt": "arquivo da memória (ex.: memory/demo.json)"},
    "mem.help_list": {"en": "shows the remembered choices", "pt": "mostra as escolhas memorizadas"},
    "mem.help_forget": {"en": "forgets choices by the number shown by 'list'",
                        "pt": "esquece escolhas pelo número mostrado em 'listar'"},
    "mem.help_clear": {"en": "forgets all choices", "pt": "esquece todas as escolhas"},
    "mem.help_yes": {"en": "does not ask for confirmation", "pt": "não pede confirmação"},
    "mem.empty": {"en": "No remembered choices.", "pt": "Nenhuma escolha memorizada."},
    "mem.count": {"en": "{count} remembered choice(s) in {path}:\n", "pt": "{count} escolha(s) memorizada(s) em {path}:\n"},
    "mem.step": {"en": '[{number}] Step: "{description}" ({action})', "pt": '[{number}] Passo: "{description}" ({action})'},
    "mem.element": {"en": "    Element: {element}", "pt": "    Elemento: {element}"},
    "mem.page": {"en": "    Page: {url}", "pt": "    Página: {url}"},
    "mem.used": {"en": "    Used {uses} time(s), last on {last}\n", "pt": "    Usada {uses} vez(es), última em {last}\n"},
    "mem.near": {"en": ", near: {near}", "pt": ", perto de: {near}"},
    "mem.no_file": {"en": "File not found: {path}", "pt": "Arquivo não encontrado: {path}"},
    "mem.invalid": {"en": "Invalid number(s): {numbers}. Use 'list' to see the numbers.",
                    "pt": "Número(s) inválido(s): {numbers}. Use 'listar' para ver os números."},
    "mem.forgotten": {"en": 'Forgotten [{number}]: "{description}" → {element}',
                      "pt": 'Esquecida [{number}]: "{description}" → {element}'},
    "mem.will_ask": {"en": "On the next run, the assistant will ask again on these steps.",
                     "pt": "Na próxima execução, o assistente vai perguntar de novo nesses passos."},
    "mem.confirm": {"en": "Forget all {total} choices? (y/n) ", "pt": "Esquecer as {total} escolhas? (s/n) "},
    "mem.nothing_deleted": {"en": "Nothing was deleted.", "pt": "Nada foi apagado."},
    "mem.cleared": {"en": "{total} choice(s) forgotten.", "pt": "{total} escolha(s) esquecida(s)."},
    # ------------------------------------------------------------ login and demo
    "session.not_logged_in": {"en": "You are not logged in.", "pt": "Usuário não está logado."},
    "session.log_in": {"en": "Please log in in the browser.", "pt": "Faça o login no navegador."},
    "session.detected": {"en": "Login detected!", "pt": "Login detectado!"},
    "session.logged_in": {"en": "You are already logged in.", "pt": "Usuário já está logado."},
    "demo.step": {"en": "- {description}: {status} (by: {by})", "pt": "- {description}: {status} (por: {by})"},
    "demo.stopped": {"en": "  Step not completed; stopping.", "pt": "  Passo não concluído; encerrando."},
    "demo.starting": {"en": "Starting the automation...", "pt": "Iniciando automação..."},
    "demo.press_enter": {"en": "Press ENTER to finish...", "pt": "Pressione ENTER para encerrar..."},
    # ------------------------------------------------------------ planner, profiles and Ollama
    "planner.gave_up": {"en": "invalid plan after {attempts} attempts: {error}",
                        "pt": "plano inválido depois de {attempts} tentativas: {error}"},
    "config.needs_key": {"en": 'Profile "{profile}" needs the environment variable {env}.\n'
                               'On Windows: setx {env} "your-key" (and open a new terminal).',
                         "pt": 'O perfil "{profile}" precisa da variável de ambiente {env}.\n'
                               'No Windows: setx {env} "sua-chave" (e abra um terminal novo).'},
    "config.no_model": {"en": 'Set the "model" field of profile "{profile}" in llm_profiles.json.',
                        "pt": 'Defina o campo "model" do perfil "{profile}" em llm_profiles.json.'},
    "config.bad_api": {"en": 'Profile "{profile}": "api" must be "openai" or "ollama", not "{api}".',
                       "pt": 'Perfil "{profile}": "api" deve ser "openai" ou "ollama", não "{api}".'},
    "config.no_file": {"en": "Profiles file not found: {path}", "pt": "Arquivo de perfis não encontrado: {path}"},
    "config.unknown_profile": {"en": 'Profile "{profile}" does not exist. Available: {available}',
                               "pt": 'Perfil "{profile}" não existe. Disponíveis: {available}'},
    "ollama.unreachable": {"en": "could not reach Ollama at {url}. Is the Ollama app running?",
                           "pt": "não consegui falar com o Ollama em {url}. O aplicativo do Ollama está aberto?"},
    "ollama.timeout": {"en": "the model did not answer within {seconds} s", "pt": "o modelo não respondeu em {seconds} s"},
    "ollama.no_model": {"en": 'model "{model}" not found in Ollama; check the name with "ollama list"',
                        "pt": 'modelo "{model}" não encontrado no Ollama; confira o nome com "ollama list"'},
    "ollama.http_error": {"en": "Ollama returned error {status}: {text}", "pt": "o Ollama devolveu erro {status}: {text}"},
    "ollama.dropped": {"en": "the connection to Ollama dropped during the answer: {error}",
                       "pt": "a conexão com o Ollama caiu durante a resposta: {error}"},
    "progress.waiting": {"en": "waiting for the model", "pt": "aguardando o modelo"},
    "progress.thinking": {"en": "model thinking", "pt": "modelo pensando"},
    "progress.writing": {"en": "writing the plan", "pt": "escrevendo o plano"},
    # ------------------------------------------------------------ agent reports
    "agent.planning": {"en": "Planning...", "pt": "Planejando..."},
    "agent.checking_end": {"en": "Checking whether anything is left...", "pt": "Conferindo se falta algo..."},
    "agent.replanning": {"en": "  {why}; replanning...", "pt": "  {why}; replanejando..."},
    "agent.why_page": {"en": "The page changed", "pt": "A página mudou"},
    "agent.why_popup_opened": {"en": "A pop-up opened", "pt": "Abriu um pop-up"},
    "agent.why_popup_closed": {"en": "A pop-up closed", "pt": "Fechou um pop-up"},
    "agent.why_attempt": {"en": "Attempt {n} of {max}", "pt": "Tentativa {n} de {max}"},
    "agent.failed_step": {"en": "    failed: {reason}", "pt": "    falhou: {reason}"},
    "agent.blocked": {"en": "  ✕ {step} (blocked: destructive action not requested)",
                      "pt": "  ✕ {step} (barrado: ação destrutiva não pedida)"},
    "agent.enter": {"en": "    no search button: Enter in the filled-in field", "pt": "    sem botão de busca: Enter no campo preenchido"},
    "agent.revealed": {"en": '    field not found: clicked "{description}" to reveal it',
                       "pt": '    campo não encontrado: clicou em "{description}" para revelá-lo'},
    "agent.retry_no_effect": {"en": "    no visible effect; trying once more", "pt": "    sem efeito visível; tentando mais uma vez"},
    "agent.skipped": {"en": "    skipped by the user", "pt": "    pulado pelo usuário"},
    "agent.done": {"en": "Done: {message}", "pt": "Concluído: {message}"},
    "agent.ended": {"en": "Stopped: {message}", "pt": "Encerrado: {message}"},
    # ------------------------------------------------------------ agent final messages
    "end.goal_reached": {"en": "goal reached", "pt": "objetivo atingido"},
    "end.all_steps": {"en": "all steps were performed", "pt": "todos os passos foram executados"},
    "end.cannot": {"en": "the request cannot be done on this page", "pt": "o pedido não pode ser feito nesta página"},
    "end.no_plan": {"en": "could not generate the plan: {error}", "pt": "não foi possível gerar o plano: {error}"},
    "end.replan_failed": {"en": "failed to replan: {error}", "pt": "falha ao replanejar: {error}"},
    "end.check_failed": {"en": "failed to check the end: {error}", "pt": "falha ao conferir o fim: {error}"},
    "end.max_steps": {"en": "limit of {max} steps reached", "pt": "limite de {max} passos atingido"},
    "end.end_checks": {"en": "the end check kept finding steps; please check the result",
                       "pt": "a conferência do fim continuou encontrando passos; confira o resultado"},
    "end.max_failures": {"en": "{max} failed attempts; last problem: {step} — {reason}",
                         "pt": "{max} tentativas sem sucesso; último problema: {step} — {reason}"},
    "end.no_other_way": {"en": "the planner found no other way after: {reason}",
                         "pt": "o planejador não encontrou outro caminho depois de: {reason}"},
    "end.pending_goals": {"en": "the planner finished with pending goals: {goals}",
                          "pt": "o planejador encerrou com metas pendentes: {goals}"},
    # ------------------------------------------------------------ command-line tools
    "cli.config_error": {"en": "Configuration error: {error}", "pt": "Erro de configuração: {error}"},
    "cli.interrupted": {"en": "Run interrupted by the user.", "pt": "Execução interrompida pelo usuário."},
    "cli.result": {"en": "Result: {status} — {message}", "pt": "Resultado: {status} — {message}"},
    "cli.summary": {"en": "Steps performed: {steps} | model calls: {calls} | replans: {replans} | failures: {failures} | "
                          "user interventions: {interventions} | tokens: {tokens_in}+{tokens_out} | time: {seconds} s",
                    "pt": "Passos executados: {steps} | chamadas ao modelo: {calls} | replanejamentos: {replans} | "
                          "falhas: {failures} | intervenções do usuário: {interventions} | tokens: {tokens_in}+{tokens_out} | "
                          "tempo: {seconds} s"},
    "cli.close_browser": {"en": "Press Enter to close the browser...", "pt": "Enter para fechar o navegador..."},
    "planner_cli.generating": {"en": "Generating the plan with {model} (the first time, this includes loading the model)...",
                               "pt": "Gerando o plano com {model} (na primeira vez, inclui carregar o modelo)..."},
    "planner_cli.invalid": {"en": "The model did not generate a valid plan: {error}", "pt": "O modelo não gerou um plano válido: {error}"},
    "planner_cli.call_failed": {"en": "Failed to call the model: {kind}: {error}", "pt": "Falha ao chamar o modelo: {kind}: {error}"},
    "planner_cli.header": {"en": "Plan ({steps} steps, {seconds}s, {tokens_in}+{tokens_out} tokens, {attempts} attempt(s)):",
                           "pt": "Plano ({steps} passos, {seconds}s, {tokens_in}+{tokens_out} tokens, {attempts} tentativa(s)):"},
    "planner_cli.goal": {"en": "  goal {id}: {description}", "pt": "  meta {id}: {description}"},
    "planner_cli.conclusive": {"en": "  (conclusive)", "pt": "  (conclusiva)"},
    "planner_cli.expects": {"en": '  → expects "{text}"', "pt": '  → espera "{text}"'},
    "demo.remembered": {"en": "I have {count} remembered choice(s) in {path}. Delete the file for the assistant to ask again.",
                        "pt": "Tenho {count} escolha(s) memorizada(s) em {path}. Apague o arquivo para o assistente perguntar de novo."},
    "demo.result": {"en": "Result: {result}", "pt": "Resultado: {result}"},
    "agent.not_fulfilled": {"en": "  The request is not fulfilled yet: {reason}", "pt": "  O pedido ainda não foi cumprido: {reason}"},
    "end.not_fulfilled": {"en": "the request was not fulfilled: {reason}", "pt": "o pedido não foi cumprido: {reason}"},
    # ------------------------------------------------------------ saved automations
    "auto.learning": {"en": 'Learning "{name}": the assistant plans the task this first time.',
                      "pt": 'Aprendendo "{name}": nesta primeira vez, o assistente planeja a tarefa.'},
    "auto.replaying": {"en": 'Running "{name}" with the approved plan ({steps} steps, no LLM).',
                       "pt": 'Executando "{name}" com o plano aprovado ({steps} passos, sem LLM).'},
    "auto.approved": {"en": "Plan approved and saved ({steps} steps): the next runs replay it.",
                      "pt": "Plano aprovado e salvo ({steps} passos): as próximas execuções o repetem."},
    "auto.broken": {"en": "the saved plan stopped working, the site may have changed: {reason}",
                    "pt": "o plano salvo deixou de funcionar, o site pode ter mudado: {reason}"},
    "auto.created": {"en": 'Automation "{name}" created in {folder}. Run it with: python -m anchor.automations run {name}',
                     "pt": 'Automação "{name}" criada em {folder}. Execute com: python -m anchor.automations run {name}'},
    "auto.none": {"en": "No saved automations yet.", "pt": "Nenhuma automação salva ainda."},
    "auto.state_approved": {"en": "approved plan, {steps} steps", "pt": "plano aprovado, {steps} passos"},
    "auto.state_new": {"en": "not learned yet (the first run learns)", "pt": "ainda não aprendida (a 1ª execução aprende)"},
    "auto.show_request": {"en": "Request: {request}", "pt": "Pedido: {request}"},
    "auto.show_url": {"en": "Link: {url}", "pt": "Link: {url}"},
    "auto.show_profile": {"en": "Model profile: {profile}", "pt": "Perfil do modelo: {profile}"},
    "auto.show_plan": {"en": "Approved plan (since {approved}):", "pt": "Plano aprovado (desde {approved}):"},
    "auto.show_runs": {"en": "Last runs ({count} in total):", "pt": "Últimas execuções ({count} no total):"},
    "auto.error": {"en": "Error: {error}", "pt": "Erro: {error}"},
    "agent.replaying": {"en": "Replaying the approved plan...", "pt": "Repetindo o plano aprovado..."},
    "agent.continuing": {"en": "  {why}; continuing with the saved plan...", "pt": "  {why}; seguindo com o plano salvo..."},
    "agent.checking_end_replay": {"en": "Checking the goals...", "pt": "Conferindo as metas..."},
    "auto.healing": {"en": "  A saved step stopped working: the assistant is planning the rest from the page as it is now...",
                     "pt": "  Um passo salvo deixou de funcionar: o assistente está planejando o resto a partir da página como ela está..."},
    "auto.heal_failed": {"en": "the saved plan stopped working and the recovery did not succeed: {reason}",
                         "pt": "o plano salvo deixou de funcionar e a recuperação não deu certo: {reason}"},
    "auto.healed": {"en": "The saved plan was corrected (recovery #{number}). Review it with: python -m anchor.automations recoveries {name}",
                    "pt": "O plano salvo foi corrigido (recuperação #{number}). Revise com: python -m anchor.automations recoveries {name}"},
    "auto.user_recovery": {"en": 'Your choice for "{description}" was remembered (recovery #{number}).',
                           "pt": 'Sua escolha para "{description}" foi memorizada (recuperação #{number}).'},
    "auto.no_recovery": {"en": "there is no recovery #{number}", "pt": "não existe a recuperação #{number}"},
    "auto.already_undone": {"en": "recovery #{number} was already undone", "pt": "a recuperação #{number} já foi desfeita"},
    "auto.no_recoveries": {"en": "No recoveries yet: the saved plan has always worked.",
                           "pt": "Nenhuma recuperação ainda: o plano salvo sempre funcionou."},
    "auto.recovery_replan": {"en": "#{number} {date}  plan corrected{undone}\n    failed: {failed}\n    reason: {reason}\n    replaced by: {replaced}\n    effect confirmed: {effect} | confidence: {confidence}",
                             "pt": "#{number} {date}  plano corrigido{undone}\n    falhou: {failed}\n    motivo: {reason}\n    substituído por: {replaced}\n    efeito confirmado: {effect} | confiança: {confidence}"},
    "auto.recovery_user": {"en": '#{number} {date}  element chosen by you for "{description}"{undone}',
                           "pt": '#{number} {date}  elemento escolhido por você para "{description}"{undone}'},
    "auto.undone_mark": {"en": "  (undone)", "pt": "  (desfeita)"},
    "auto.yes": {"en": "yes", "pt": "sim"},
    "auto.no": {"en": "no", "pt": "não"},
    "auto.undo_replan": {"en": "Recovery #{number} undone: the plan from before it is back.",
                         "pt": "Recuperação #{number} desfeita: o plano anterior a ela voltou."},
    "auto.undo_user": {"en": 'Recovery #{number} undone: the choice for "{description}" was forgotten; the next run asks again.',
                       "pt": 'Recuperação #{number} desfeita: a escolha para "{description}" foi esquecida; a próxima execução pergunta de novo.'},
    "auto.parameters": {"en": "Parameters: {names} (give them with --param name=value, or --csv file.csv)",
                        "pt": "Parâmetros: {names} (informe com --param nome=valor, ou --csv arquivo.csv)"},
    "auto.row": {"en": "=== Row {number} of {total}", "pt": "=== Linha {number} de {total}"},
    "auto.csv_empty": {"en": "the file {path} has no rows", "pt": "o arquivo {path} não tem linhas"},
    "auto.csv_summary": {"en": "Rows done: {done} of {total}.", "pt": "Linhas cumpridas: {done} de {total}."},
    "auto.ask_note": {"en": "Want to leave a note for the next runs (e.g. where the button is)? Enter to skip:",
                      "pt": "Quer deixar uma observação para as próximas execuções (ex.: onde fica o botão)? Enter para pular:"},
    "auto.note_saved": {"en": "Note #{number} saved: the planner will read it in the next runs.",
                        "pt": "Observação #{number} salva: o planejador vai lê-la nas próximas execuções."},
    "auto.note_removed": {"en": "Note #{number} removed.", "pt": "Observação #{number} removida."},
    "auto.no_note": {"en": "there is no note #{number}", "pt": "não existe a observação #{number}"},
    "auto.no_notes": {"en": "No notes yet.", "pt": "Nenhuma observação ainda."},
    "auto.note_not_sent": {"en": "  (older: not sent to the planner)", "pt": "  (antiga: não vai para o planejador)"},
    "end.denied": {"en": "stopped: you did not allow {step}", "pt": "interrompido: você não permitiu {step}"},
    # ------------------------------------------------------------ sensitive actions
    "confirm.ask": {"en": '  Sensitive action ({category}): "{element}" (step: {description}).',
                    "pt": '  Ação sensível ({category}): "{element}" (passo: {description}).'},
    "confirm.prompt": {"en": "  Allow it? [y/N]", "pt": "  Permitir? [s/N]"},
    "confirm.no_terminal": {"en": "  No one to confirm it (no terminal): not allowed.",
                            "pt": "  Ninguém para confirmar (sem terminal): não permitida."},
    "confirm.cat_delete": {"en": "delete", "pt": "excluir"},
    "confirm.cat_submit": {"en": "save or submit", "pt": "salvar ou enviar dados"},
    "confirm.cat_send": {"en": "send", "pt": "enviar"},
    "confirm.cat_pay": {"en": "pay or buy", "pt": "pagar ou comprar"},
    "confirm.cat_download": {"en": "download", "pt": "baixar"},
    "confirm.cat_upload": {"en": "upload", "pt": "enviar arquivo"},
    "confirm.saved_allowed": {"en": "  Allowed (decision #{number}): the next runs will not ask again.",
                              "pt": "  Permitida (decisão #{number}): as próximas execuções não perguntam de novo."},
    "confirm.saved_denied": {"en": "  Not allowed (decision #{number}): the next runs stop here too.",
                             "pt": "  Não permitida (decisão #{number}): as próximas execuções também param aqui."},
    "confirm.denied_before": {"en": '  You did not allow "{element}" before (decision #{number}). To change it: python -m anchor.automations confirmations {name} --forget {number}',
                              "pt": '  Você não permitiu "{element}" antes (decisão #{number}). Para mudar: python -m anchor.automations confirmations {name} --forget {number}'},
    "confirm.none": {"en": "No decisions on sensitive actions yet.", "pt": "Nenhuma decisão sobre ações sensíveis ainda."},
    "confirm.item": {"en": "  #{number} {date}  {decision:8} {category:9} {element}",
                     "pt": "  #{number} {date}  {decision:8} {category:9} {element}"},
    "confirm.allowed": {"en": "allowed", "pt": "permitida"},
    "confirm.denied": {"en": "denied", "pt": "negada"},
    "confirm.forgotten": {"en": "Decision #{number} forgotten: the next run asks again.",
                          "pt": "Decisão #{number} esquecida: a próxima execução pergunta de novo."},
    "confirm.no_decision": {"en": "there is no decision #{number}", "pt": "não existe a decisão #{number}"},
}
