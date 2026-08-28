/* Painel de certidões — sem framework, sem build: abre e funciona. */

const estado = {
  pagina: "painel",
  filtro: null,
  tipos: [],
  titulares: [],
  painel: [],
  desafioAtual: null,
  desafios: [],
  desafiosAdiados: new Set(),
  resumo: null,
};

const $ = (seletor) => document.querySelector(seletor);
const el = (tag, atributos = {}, filhos = []) => {
  const no = document.createElement(tag);
  for (const [chave, valor] of Object.entries(atributos)) {
    if (chave === "class") no.className = valor;
    else if (chave === "html") no.innerHTML = valor;
    else if (chave.startsWith("on")) no.addEventListener(chave.slice(2), valor);
    else if (valor !== null && valor !== undefined) no.setAttribute(chave, valor);
  }
  for (const filho of [].concat(filhos)) {
    if (filho === null || filho === undefined) continue;
    no.append(filho.nodeType ? filho : document.createTextNode(filho));
  }
  return no;
};

/* ------------------------------------------------------------------ avisos */
function avisar(texto, tipo = "") {
  const aviso = el("div", { class: `aviso ${tipo}` }, texto);
  $("#avisos").append(aviso);
  setTimeout(() => aviso.remove(), 5000);
}

/* --------------------------------------------------------------------- api */
async function api(caminho, opcoes = {}) {
  const resposta = await fetch(caminho, {
    headers: opcoes.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...opcoes,
  });
  const texto = await resposta.text();
  const dados = texto ? JSON.parse(texto) : null;
  if (!resposta.ok) {
    const mensagem = dados?.erro || dados?.detail || "Não foi possível concluir a operação.";
    avisar(typeof mensagem === "string" ? mensagem : "Erro inesperado.", "erro");
    throw new Error(mensagem);
  }
  return dados;
}

/* ---------------------------------------------------------------- formatos */
const dataBR = (iso) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—");

function prazoLegivel(dias) {
  if (dias === null || dias === undefined) return "";
  if (dias < 0) return `vencida há ${Math.abs(dias)} dia${Math.abs(dias) === 1 ? "" : "s"}`;
  if (dias === 0) return "vence hoje";
  if (dias === 1) return "vence amanhã";
  return `${dias} dias restantes`;
}

const ROTULO_ESTADO = {
  na_fila: "Na fila",
  executando: "Em andamento",
  aguardando_humano: "Precisa de você",
  aguardando_anexo: "Aguardando o PDF",
  concluida: "Concluída",
  falhou: "Falhou",
  cancelada: "Cancelada",
};

function mascararDocumento(valor) {
  const digitos = valor.replace(/\D/g, "").slice(0, 14);
  if (digitos.length <= 11) {
    return digitos
      .replace(/^(\d{3})(\d)/, "$1.$2")
      .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d{1,2})$/, ".$1-$2");
  }
  return digitos
    .replace(/^(\d{2})(\d)/, "$1.$2")
    .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1/$2")
    .replace(/(\d{4})(\d{1,2})$/, "$1-$2");
}

/* ------------------------------------------------------------------ modais */
function abrirModal(titulo, corpo, botoes = []) {
  $("#modal-titulo").textContent = titulo;
  $("#modal-corpo").replaceChildren(corpo);
  $("#modal-rodape").replaceChildren(...botoes);
  $("#cortina").classList.remove("oculto");
}
const fecharModal = () => $("#cortina").classList.add("oculto");

/* Excluir é definitivo: a pessoa precisa ver o que perde antes de decidir. */
function confirmar(titulo, corpo, rotulo = "Excluir") {
  return new Promise((resolver) => {
    const cancelar = el("button", { class: "botao secundario", onclick: () => { fecharModal(); resolver(false); } }, "Cancelar");
    const confirmarBotao = el("button", { class: "botao perigo", onclick: () => { fecharModal(); resolver(true); } }, rotulo);
    abrirModal(titulo, typeof corpo === "string" ? el("div", {}, corpo) : corpo, [cancelar, confirmarBotao]);
  });
}

/* ------------------------------------------------------------------ painel */
function cartao(valor, rotulo, classe, aoClicar) {
  return el("div", { class: `cartao ${classe}`, ...(aoClicar ? { onclick: aoClicar } : {}) }, [
    el("div", { class: "valor" }, String(valor)),
    el("div", { class: "rotulo" }, rotulo),
  ]);
}

function desenharCartoes() {
  const r = estado.resumo;
  if (!r) return;
  const p = r.por_status;
  const cartoes = [
    cartao(p.vencida + p.ausente, "Vencidas ou nunca emitidas", "alerta", () => filtrar("vencida,ausente")),
    cartao(p.vence_em_breve, "Vencem nos próximos dias", "atencao", () => filtrar("vence_em_breve")),
    cartao(p.vigente, "Vigentes", "bom", () => filtrar("vigente")),
    cartao(p.irregular, "Positivas (com débitos)", "acao", () => filtrar("irregular")),
  ];
  if (r.aguardando_humano > 0) {
    cartoes.push(cartao(r.aguardando_humano, "Pedidos de ajuda abertos", "acao", () => irPara("solicitacoes")));
  }
  $("#cartoes").replaceChildren(...cartoes);
}

function filtrar(status) {
  estado.filtro = estado.filtro === status ? null : status;
  irPara("painel");
  desenharPainel();
}

function desenharFiltros() {
  const opcoes = [
    ["Tudo", null],
    ["Vencidas", "vencida"],
    ["Vencendo", "vence_em_breve"],
    ["Não emitidas", "ausente"],
    ["Vigentes", "vigente"],
  ];
  $("#filtros-status").replaceChildren(
    ...opcoes.map(([rotulo, valor]) =>
      el("button", {
        class: `filtro ${estado.filtro === valor ? "ativo" : ""}`,
        onclick: () => { estado.filtro = valor; desenharPainel(); },
      }, rotulo)
    )
  );
}

function desenharPainel() {
  desenharFiltros();
  const permitidos = estado.filtro ? estado.filtro.split(",") : null;
  const linhas = estado.painel.filter((l) => !permitidos || permitidos.includes(l.status));

  if (!estado.painel.length) {
    $("#tabela-painel").replaceChildren(primeirosPassos());
    return;
  }

  const corpo = linhas.map((linha) => {
    const acoes = [];
    if (linha.solicitacao_em_andamento) {
      acoes.push(el("span", { class: "pilula andamento" }, ROTULO_ESTADO[linha.estado_solicitacao] || "Em andamento"));
    } else {
      const rotulo = linha.status === "ausente" ? "Emitir" : "Renovar";
      const tipo = estado.tipos.find((x) => x.id === linha.tipo_id);
      const alternativas = (tipo?.fontes || []).filter((f) => !f.padrao);
      acoes.push(el("button", {
        class: "botao secundario miudo",
        onclick: (evento) => emitir(linha, evento.target),
      }, rotulo));
      if (alternativas.length) {
        // Mais de um caminho para a mesma certidão: o site (grátis) e a API
        // contratada (paga, sem captcha). A escolha é do escritório.
        acoes.push(el("button", {
          class: "botao secundario miudo",
          style: "margin-left:6px",
          title: "Escolher por onde emitir",
          onclick: () => escolherFonte(linha, tipo),
        }, "⋯"));
      }
    }
    if (linha.certidao_id && linha.tem_arquivo) {
      acoes.push(el("a", {
        class: "botao secundario miudo",
        href: `/api/certidoes/${linha.certidao_id}/arquivo`,
        target: "_blank",
        style: "margin-left:6px; text-decoration:none;",
      }, "PDF"));
    }

    return el("tr", {}, [
      el("td", {}, [
        el("div", { class: "principal" }, linha.titular),
        el("div", { class: "secundaria" }, linha.documento),
      ]),
      el("td", {}, [
        el("div", {}, linha.tipo),
        el("div", { class: "secundaria" }, `${linha.orgao} · ${linha.esfera}`),
      ]),
      el("td", {}, [
        el("span", { class: `pilula ${linha.status}` }, linha.status_rotulo),
        el("div", { class: "secundaria" }, linha.status === "irregular"
          ? "há débitos em aberto — reemitir não resolve"
          : prazoLegivel(linha.dias_restantes)),
      ]),
      el("td", {}, [
        el("div", {}, linha.valida_ate ? dataBR(linha.valida_ate) : "—"),
        el("div", { class: "secundaria" }, linha.emitida_em ? `emitida ${dataBR(linha.emitida_em)}` : ""),
      ]),
      el("td", { class: "acoes" }, acoes),
    ]);
  });

  const tabela = el("table", {}, [
    el("thead", {}, el("tr", {}, ["Titular", "Certidão", "Situação", "Validade", ""].map((t) =>
      el("th", {}, t)))),
    el("tbody", {}, corpo),
  ]);
  $("#tabela-painel").replaceChildren(tabela);
}

function passo(numero, titulo, texto, acao) {
  return el("div", { style: "display:flex; gap:14px; align-items:flex-start; padding:14px 0; border-top:1px solid var(--borda)" }, [
    el("div", {
      style: "flex-shrink:0; width:28px; height:28px; border-radius:50%; background:var(--primaria-clara);" +
             "color:var(--primaria); display:grid; place-items:center; font-weight:700; font-size:14px",
    }, String(numero)),
    el("div", { style: "flex:1" }, [
      el("div", { class: "principal" }, titulo),
      el("div", { class: "secundaria", style: "margin:2px 0 8px" }, texto),
      acao,
    ]),
  ]);
}

function primeirosPassos() {
  return el("div", { style: "padding:22px 26px" }, [
    el("h3", { style: "margin:0 0 4px" }, "Primeiros passos"),
    el("p", { class: "apoio", style: "margin-bottom:6px" },
      "Três coisas e o sistema passa a trabalhar sozinho."),
    passo(1, "Cadastre um titular",
      "A pessoa ou empresa e quais certidões ela precisa manter vigentes.",
      el("button", { class: "botao primario miudo", onclick: () => formularioTitular() },
        "Cadastrar titular")),
    passo(2, "Confira as fontes",
      "O sistema abre cada site de órgão e verifica se ainda sabe operá-lo. Não emite nada.",
      el("button", { class: "botao secundario miudo", onclick: () => irPara("configuracoes") },
        "Ir para a conferência")),
    passo(3, "Deixe emitir",
      "O painel mostra o que falta e o sistema renova antes de vencer. Quando um site pedir " +
      "captcha ou login gov.br, esta tela avisa.",
      el("span", { class: "secundaria" }, "Nada a fazer agora.")),
  ]);
}

function descricaoDaFonte(fonte) {
  if (fonte.tipo !== "api") return "opera o site do órgão, sem custo";
  const preco = fonte.custo
    ? `R$ ${fonte.custo.toFixed(2).replace(".", ",")} por emissão`
    : "cobrada por consulta, conforme o contrato";
  return `API contratada — sem captcha, ${preco}`;
}

function escolherFonte(linha, tipo) {
  const opcoes = (tipo.fontes || []).map((fonte) =>
    el("div", {
      class: "escolha",
      style: "cursor:pointer",
      onclick: async () => { fecharModal(); await emitir(linha, null, fonte.codigo); },
    }, [
      el("div", {}, [
        el("div", { class: "nome" }, fonte.nome + (fonte.padrao ? " (padrão)" : "")),
        el("div", { class: "detalhe" }, descricaoDaFonte(fonte)),
      ]),
    ])
  );
  abrirModal(`Emitir ${linha.sigla} — por onde?`, el("div", {}, [
    el("p", { class: "apoio" }, `${linha.tipo} — ${linha.titular}`),
    el("div", { class: "escolhas" }, opcoes),
    el("p", { class: "apoio", style: "margin-top:10px" },
      "A fonte paga só funciona depois de cadastrar o token em Configurações › Credenciais de API."),
  ]), [el("button", { class: "botao secundario", onclick: fecharModal }, "Cancelar")]);
}

async function emitir(linha, botao, fonte = null) {
  if (botao) { botao.disabled = true; botao.textContent = "Enviando..."; }
  try {
    await api("/api/solicitacoes", {
      method: "POST",
      body: JSON.stringify({
        titular_id: linha.titular_id, tipo_id: linha.tipo_id, ...(fonte ? { fonte } : {}),
      }),
    });
    avisar(`${linha.sigla} de ${linha.titular} entrou na fila.`, "bom");
    await carregar();
  } finally {
    if (botao) botao.disabled = false;
  }
}

/* --------------------------------------------------------------- titulares */
function desenharTitulares() {
  if (!estado.titulares.length) {
    $("#lista-titulares").replaceChildren(
      el("div", { class: "vazio" }, [
        el("strong", {}, "Nenhum titular cadastrado"),
        el("div", {}, "Cadastre a pessoa ou empresa para começar a acompanhar as certidões dela."),
      ])
    );
    return;
  }
  const linhas = estado.titulares.map((t) =>
    el("tr", {}, [
      el("td", {}, [
        el("div", { class: "principal" }, t.nome),
        el("div", { class: "secundaria" }, `${t.documento_formatado} · ${t.tipo === "PF" ? "pessoa física" : "pessoa jurídica"}`),
      ]),
      el("td", {}, [t.municipio, t.uf].filter(Boolean).join(" / ") || "—"),
      el("td", {}, `${t.monitoramentos.length} certidão(ões)`),
      el("td", { class: "acoes" }, [
        el("a", {
          class: "botao secundario miudo", href: `/api/titulares/${t.id}/dossie`, target: "_blank",
          title: "Um PDF único com as certidões vigentes deste titular",
          style: "text-decoration:none; margin-right:6px",
        }, "Dossiê"),
        el("button", { class: "botao secundario miudo", onclick: () => formularioTitular(t) }, "Editar"),
      ]),
    ])
  );
  $("#lista-titulares").replaceChildren(
    el("table", {}, [
      el("thead", {}, el("tr", {}, ["Titular", "Local", "Acompanhando", ""].map((t) => el("th", {}, t)))),
      el("tbody", {}, linhas),
    ])
  );
}

function formularioTitular(titular = null) {
  const dados = titular || { monitoramentos: [], tipo: "PJ" };
  const campo = (rotulo, entrada, dica) =>
    el("div", { class: "campo" }, [
      el("label", {}, [rotulo, dica ? el("span", { class: "dica" }, ` — ${dica}`) : null]),
      entrada,
    ]);

  const entradaNome = el("input", { type: "text", value: dados.nome || "", placeholder: "Nome completo ou razão social" });
  const entradaDoc = el("input", { type: "text", value: dados.documento_formatado || "", placeholder: "CPF ou CNPJ" });
  entradaDoc.addEventListener("input", () => { entradaDoc.value = mascararDocumento(entradaDoc.value); atualizarEscolhas(); });
  const entradaUf = el("input", { type: "text", value: dados.uf || "", maxlength: "2", placeholder: "SP" });
  const entradaMunicipio = el("input", { type: "text", value: dados.municipio || "", placeholder: "São Paulo" });
  const entradaEmail = el("input", { type: "email", value: dados.email || "", placeholder: "para avisos de vencimento" });
  const entradaDias = el("input", { type: "number", value: "15", min: "1", max: "120" });
  const entradaRenovar = el("input", { type: "checkbox", checked: "checked" });
  const caixaEscolhas = el("div", { class: "escolhas" });

  // Mantém a escolha do usuário mesmo quando a lista é redesenhada ao trocar
  // o documento (as certidões aplicáveis a PF e a PJ não são as mesmas).
  const selecionados = new Set(dados.monitoramentos || []);

  function atualizarEscolhas() {
    const digitos = entradaDoc.value.replace(/\D/g, "");
    const pf = digitos.length > 0 && digitos.length <= 11;
    const aplicaveis = estado.tipos.filter((t) => t.ativo && (pf ? t.aplica_pf : t.aplica_pj));
    caixaEscolhas.replaceChildren(
      ...aplicaveis.map((tipo) => {
        const marcado = selecionados.has(tipo.id);
        const detalhes = [
          tipo.orgao,
          `validade ${tipo.validade_dias} dias`,
          tipo.requer_gov_br ? "exige gov.br" : null,
          tipo.captcha !== "nenhum" ? `captcha: ${tipo.captcha}` : null,
        ].filter(Boolean).join(" · ");
        const marca = el("input", {
          type: "checkbox", value: String(tipo.id), ...(marcado ? { checked: "checked" } : {}),
        });
        marca.addEventListener("change", () => {
          if (marca.checked) selecionados.add(tipo.id);
          else selecionados.delete(tipo.id);
        });
        return el("label", { class: "escolha" }, [
          marca,
          el("div", {}, [
            el("div", { class: "nome" }, tipo.nome),
            el("div", { class: "detalhe" }, detalhes),
          ]),
        ]);
      })
    );
    if (!aplicaveis.length) {
      caixaEscolhas.replaceChildren(el("div", { class: "detalhe" }, "Digite o CPF ou CNPJ para ver as certidões aplicáveis."));
    }
  }
  atualizarEscolhas();

  const corpo = el("div", {}, [
    campo("Nome", entradaNome),
    campo("CPF ou CNPJ", entradaDoc, "define quais certidões se aplicam"),
    el("div", { class: "linha" }, [campo("UF", entradaUf), campo("Município", entradaMunicipio)]),
    campo("E-mail", entradaEmail, "opcional"),
    el("div", { class: "campo" }, [
      el("label", {}, "Certidões que este titular precisa manter vigentes"),
      caixaEscolhas,
    ]),
    el("div", { class: "linha" }, [
      campo("Avisar/renovar com quantos dias de antecedência", entradaDias),
      el("div", { class: "campo" }, [
        el("label", {}, "Renovação"),
        el("label", { class: "alternador" }, [entradaRenovar, "renovar automaticamente ao se aproximar do vencimento"]),
      ]),
    ]),
  ]);

  const salvar = el("button", { class: "botao primario" }, "Salvar");
  salvar.addEventListener("click", async () => {
    salvar.disabled = true;
    try {
      const corpoRequisicao = {
        nome: entradaNome.value.trim(),
        documento: entradaDoc.value,
        uf: entradaUf.value,
        municipio: entradaMunicipio.value,
        email: entradaEmail.value,
        monitoramentos: [...selecionados],
        dias_antecedencia: Number(entradaDias.value) || 15,
        renovar_automaticamente: entradaRenovar.checked,
      };
      await api(titular ? `/api/titulares/${titular.id}` : "/api/titulares", {
        method: titular ? "PUT" : "POST",
        body: JSON.stringify(corpoRequisicao),
      });
      fecharModal();
      avisar("Titular salvo.", "bom");
      await carregar();
    } finally {
      salvar.disabled = false;
    }
  });

  const botoes = [el("button", { class: "botao secundario", onclick: fecharModal }, "Cancelar"), salvar];
  if (titular) {
    const excluir = el("button", { class: "botao perigo", style: "margin-right:auto" }, "Excluir titular");
    excluir.addEventListener("click", async () => {
      const previa = await api(`/api/titulares/${titular.id}/o-que-sera-excluido`);
      fecharModal();
      const certeza = await confirmar(`Excluir ${previa.titular}?`,
        el("div", {}, [
          el("p", {}, "Serão apagados definitivamente:"),
          el("ul", {}, [
            el("li", {}, `${previa.certidoes} certidão(ões) arquivada(s), com os PDFs`),
            el("li", {}, `${previa.solicitacoes} solicitação(ões)`),
            el("li", {}, "o cadastro e o acompanhamento de vencimentos"),
          ]),
          el("p", { class: "apoio" },
            "Não tem volta. Se a intenção é só parar de acompanhar, desmarque as certidões " +
            "no cadastro em vez de excluir."),
        ]), "Excluir definitivamente");
      if (!certeza) return;
      await api(`/api/titulares/${titular.id}?definitivo=true`, { method: "DELETE" });
      avisar(`${previa.titular} foi excluído.`);
      await carregar();
    });
    botoes.unshift(excluir);
  }
  abrirModal(titular ? "Editar titular" : "Novo titular", corpo, botoes);
}

/* ------------------------------------------------------------ solicitações */
async function desenharSolicitacoes() {
  const itens = await api("/api/solicitacoes?limite=60");
  const emAndamento = itens.filter((s) => !["concluida", "falhou", "cancelada"].includes(s.estado)).length;
  $("#contador-solicitacoes").textContent = emAndamento || "";

  if (!itens.length) {
    $("#lista-solicitacoes").replaceChildren(
      el("div", { class: "vazio" }, [el("strong", {}, "Nada por aqui ainda"),
        el("div", {}, "As emissões pedidas no painel aparecem nesta lista.")])
    );
    return;
  }

  const linhas = itens.map((item) => {
    const acoes = [];
    if (item.estado === "aguardando_anexo") {
      acoes.push(el("button", { class: "botao primario miudo", onclick: () => formularioAnexo(item) }, "Anexar PDF"));
    }
    if (item.estado === "falhou" || item.estado === "cancelada") {
      acoes.push(el("button", { class: "botao secundario miudo", onclick: () => reenviar(item) }, "Tentar de novo"));
    }
    if (["na_fila", "executando", "aguardando_humano", "aguardando_anexo"].includes(item.estado)) {
      acoes.push(el("button", { class: "botao secundario miudo", onclick: () => cancelar(item) }, "Cancelar"));
    }
    acoes.push(el("button", { class: "botao secundario miudo", onclick: () => detalhes(item) }, "Detalhes"));
    if (["concluida", "falhou", "cancelada", "aguardando_anexo"].includes(item.estado)) {
      acoes.push(el("button", {
        class: "botao secundario miudo", style: "margin-left:6px",
        onclick: async () => {
          const certeza = await confirmar("Excluir esta solicitação?",
            "Some da lista o registro desta tentativa. A certidão já arquivada, se houver, " +
            "continua no acervo.");
          if (!certeza) return;
          await api(`/api/solicitacoes/${item.id}`, { method: "DELETE" });
          avisar("Solicitação excluída.");
          await carregar();
        },
      }, "Excluir"));
    }

    return el("tr", {}, [
      el("td", {}, [
        el("div", { class: "principal" }, item.titular),
        el("div", { class: "secundaria" }, item.tipo),
      ]),
      el("td", {}, [
        el("span", { class: `pilula ${classeEstado(item.estado)}` }, ROTULO_ESTADO[item.estado] || item.estado),
        item.origem === "renovacao" ? el("div", { class: "secundaria" }, "renovação automática") : null,
      ]),
      el("td", { class: "secundaria" }, item.mensagem || ""),
      el("td", { class: "acoes" }, acoes),
    ]);
  });

  $("#lista-solicitacoes").replaceChildren(
    el("table", {}, [
      el("thead", {}, el("tr", {}, ["Solicitação", "Estado", "Último retorno", ""].map((t) => el("th", {}, t)))),
      el("tbody", {}, linhas),
    ])
  );
}

const classeEstado = (estadoSolicitacao) => ({
  concluida: "vigente",
  falhou: "vencida",
  cancelada: "ausente",
  aguardando_humano: "irregular",
  aguardando_anexo: "vence_em_breve",
}[estadoSolicitacao] || "andamento");

function detalhes(item) {
  const registro = (item.registro || [])
    .map((r) => `${r.em}  ${r.tipo}: ${r.mensagem}`)
    .join("\n") || "Sem registro de execução.";
  abrirModal(`${item.tipo} — ${item.titular}`, el("div", {}, [
    el("p", { class: "apoio" }, `Estado: ${ROTULO_ESTADO[item.estado] || item.estado} · tentativas: ${item.tentativas}`),
    item.mensagem ? el("p", {}, item.mensagem) : null,
    el("div", { class: "registro" }, registro),
    item.diagnostico ? el("p", { class: "apoio", style: "margin-top:12px" }, `Detalhe técnico: ${item.diagnostico}`) : null,
  ]), [el("button", { class: "botao secundario", onclick: fecharModal }, "Fechar")]);
}

function formularioAnexo(item) {
  const entradaArquivo = el("input", { type: "file", accept: "application/pdf" });
  const entradaEmissao = el("input", { type: "date" });
  const entradaValidade = el("input", { type: "date" });
  const corpo = el("div", {}, [
    el("div", { class: "instrucao" }, item.mensagem || "Anexe o PDF emitido no site do órgão."),
    el("div", { class: "campo" }, [el("label", {}, "Arquivo PDF"), entradaArquivo]),
    el("div", { class: "linha" }, [
      el("div", { class: "campo" }, [el("label", {}, [ "Emitida em ", el("span", { class: "dica" }, "opcional")]), entradaEmissao]),
      el("div", { class: "campo" }, [el("label", {}, ["Válida até ", el("span", { class: "dica" }, "opcional")]), entradaValidade]),
    ]),
    el("p", { class: "apoio" }, "Se as datas ficarem em branco, o sistema tenta lê-las no próprio PDF e, se não achar, usa a validade padrão do tipo."),
  ]);
  const enviar = el("button", { class: "botao primario" }, "Anexar");
  enviar.addEventListener("click", async () => {
    if (!entradaArquivo.files.length) return avisar("Escolha o arquivo PDF.", "erro");
    const formulario = new FormData();
    formulario.append("arquivo", entradaArquivo.files[0]);
    const parametros = new URLSearchParams();
    if (entradaEmissao.value) parametros.set("emitida_em", entradaEmissao.value);
    if (entradaValidade.value) parametros.set("valida_ate", entradaValidade.value);
    enviar.disabled = true;
    try {
      await api(`/api/solicitacoes/${item.id}/anexar?${parametros}`, { method: "POST", body: formulario });
      fecharModal();
      avisar("Certidão arquivada.", "bom");
      await carregar();
    } finally {
      enviar.disabled = false;
    }
  });
  abrirModal("Anexar certidão", corpo, [
    el("button", { class: "botao secundario", onclick: fecharModal }, "Cancelar"), enviar,
  ]);
}

async function reenviar(item) {
  await api(`/api/solicitacoes/${item.id}/reenviar`, { method: "POST" });
  avisar("Solicitação reenviada.", "bom");
  await carregar();
}

async function cancelar(item) {
  await api(`/api/solicitacoes/${item.id}/cancelar`, { method: "POST" });
  avisar("Solicitação cancelada.");
  await carregar();
}

/* -------------------------------------------------------------------- acervo */
async function desenharAcervo() {
  const incluir = $("#incluir-substituidas").checked;
  const itens = await api(`/api/certidoes?incluir_substituidas=${incluir}`);
  if (!itens.length) {
    $("#lista-acervo").replaceChildren(
      el("div", { class: "vazio" }, [el("strong", {}, "Nenhum documento arquivado ainda")])
    );
    return;
  }
  const linhas = itens.map((c) =>
    el("tr", {}, [
      el("td", {}, [
        el("div", { class: "principal" }, c.titular),
        el("div", { class: "secundaria" }, c.tipo),
      ]),
      el("td", {}, [
        el("div", {}, `${dataBR(c.emitida_em)} → ${dataBR(c.valida_ate)}`),
        el("div", { class: "secundaria" }, c.numero || ""),
      ]),
      el("td", {}, [
        el("span", { class: "etiqueta" }, c.situacao.replaceAll("_", " ")),
        c.substituida ? el("span", { class: "etiqueta" }, "substituída") : null,
        c.origem === "upload" ? el("span", { class: "etiqueta" }, "anexada") : null,
      ]),
      el("td", { class: "acoes" }, [
        c.tem_arquivo
          ? el("a", { class: "botao secundario miudo", href: `/api/certidoes/${c.id}/arquivo`,
                      target: "_blank", style: "text-decoration:none; margin-right:6px" }, "Abrir PDF")
          : el("span", { class: "secundaria", style: "margin-right:6px" }, "sem arquivo"),
        el("button", {
          class: "botao secundario miudo",
          onclick: async () => {
            const certeza = await confirmar("Excluir esta certidão do acervo?",
              `${c.tipo} de ${c.titular}, válida até ${dataBR(c.valida_ate)}. ` +
              "O PDF é apagado junto. Se houver uma versão anterior, ela volta a valer.");
            if (!certeza) return;
            await api(`/api/certidoes/${c.id}`, { method: "DELETE" });
            avisar("Certidão excluída.");
            await carregar();
            await desenharAcervo();
          },
        }, "Excluir"),
      ]),
    ])
  );
  $("#lista-acervo").replaceChildren(
    el("table", {}, [
      el("thead", {}, el("tr", {}, ["Documento", "Vigência", "Situação", ""].map((t) => el("th", {}, t)))),
      el("tbody", {}, linhas),
    ])
  );
}

/* ------------------------------------------------------------------ catálogo */
function desenharCatalogo() {
  const linhas = estado.tipos.map((tipo) => {
    const marcas = [
      el("span", { class: "etiqueta" }, tipo.esfera),
      tipo.requer_gov_br ? el("span", { class: "etiqueta" }, "gov.br") : null,
      tipo.captcha !== "nenhum" ? el("span", { class: "etiqueta" }, `captcha ${tipo.captcha}`) : null,
      el("span", { class: "etiqueta" }, tipo.modo),
      tipo.verificado_em
        ? el("span", { class: "etiqueta" }, `fonte conferida em ${dataBR(tipo.verificado_em)}`)
        : el("span", { class: "etiqueta" }, "fonte não conferida"),
      ...(tipo.fontes || []).filter((f) => f.tipo === "api")
        .map((f) => el("span", { class: "etiqueta" }, "API disponível")),
    ].filter(Boolean);
    return el("tr", {}, [
      el("td", {}, [
        el("div", { class: "principal" }, tipo.nome),
        el("div", { class: "secundaria" }, tipo.orgao),
        el("div", { style: "margin-top:4px" }, marcas),
      ]),
      el("td", {}, `${tipo.validade_dias} dias`),
      el("td", { class: "secundaria", style: "max-width:320px" }, tipo.observacoes || ""),
      el("td", { class: "acoes" }, el("button", {
        class: "botao secundario miudo", onclick: () => formularioTipo(tipo),
      }, "Ajustar")),
    ]);
  });
  $("#lista-catalogo").replaceChildren(
    el("table", {}, [
      el("thead", {}, el("tr", {}, ["Certidão", "Validade padrão", "Observações", ""].map((t) => el("th", {}, t)))),
      el("tbody", {}, linhas),
    ])
  );
}

function formularioTipo(tipo) {
  const entradaUrl = el("input", { type: "text", value: tipo.url || "", placeholder: "https://..." });
  const entradaValidade = el("input", { type: "number", value: String(tipo.validade_dias), min: "1" });
  const corpo = el("div", {}, [
    el("div", { class: "campo" }, [
      el("label", {}, ["Endereço de emissão ", el("span", { class: "dica" }, "o site que o sistema abre")]),
      entradaUrl,
    ]),
    el("div", { class: "campo" }, [
      el("label", {}, ["Validade padrão (dias) ",
        el("span", { class: "dica" }, "usada quando o PDF não informa a data")]),
      entradaValidade,
    ]),
    tipo.observacoes ? el("p", { class: "apoio" }, tipo.observacoes) : null,
  ]);
  const salvar = el("button", { class: "botao primario" }, "Salvar");
  salvar.addEventListener("click", async () => {
    await api(`/api/tipos/${tipo.id}`, {
      method: "PUT",
      body: JSON.stringify({ url: entradaUrl.value, validade_dias: Number(entradaValidade.value) }),
    });
    fecharModal();
    avisar("Catálogo atualizado.", "bom");
    await carregar();
  });
  abrirModal(tipo.nome, corpo, [
    el("button", { class: "botao secundario", onclick: fecharModal }, "Cancelar"), salvar,
  ]);
}

/* ------------------------------------------------------ sala de captchas */
/* Vários pedidos de ajuda chegam juntos de propósito: as emissões com captcha
   de letras rodam em paralelo, então a pessoa responde uma imagem atrás da
   outra, sem esperar cada site carregar. Responder já mostra a próxima. */

let salaAberta = false;

const PRECISA_DIGITAR = new Set(["captcha_imagem"]);

async function atualizarDesafios() {
  let abertos = [];
  try {
    abertos = await fetch("/api/desafios").then((r) => (r.ok ? r.json() : []));
  } catch {
    return;
  }
  const idsAbertos = new Set(abertos.map((d) => d.id));
  for (const id of estado.desafiosAdiados) {
    if (!idsAbertos.has(id)) estado.desafiosAdiados.delete(id);
  }
  estado.desafios = abertos.filter((d) => !estado.desafiosAdiados.has(d.id));
  if (!estado.desafios.length) return fecharSala();
  if (!salaAberta) salaAberta = true;
  desenharSala();
}

function fecharSala() {
  if (!salaAberta) return;
  salaAberta = false;
  estado.desafioAtual = null;
  $("#cortina-desafio").classList.add("oculto");
  carregar();
}

function desenharSala() {
  const desafio = estado.desafios[0];
  if (!desafio) return fecharSala();
  const mesmo = estado.desafioAtual?.id === desafio.id;
  estado.desafioAtual = desafio;

  const digitar = PRECISA_DIGITAR.has(desafio.tipo);
  const restantes = estado.desafios.length;
  const entrada = el("input", {
    type: "text", placeholder: "Digite e tecle Enter", autocomplete: "off", spellcheck: "false",
  });
  entrada.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); enviarResposta(entrada.value.trim()); }
  });

  $("#desafio-titulo").textContent = digitar
    ? (restantes > 1 ? `Captchas — faltam ${restantes}` : "Digite o captcha")
    : "O sistema precisa de você";

  $("#desafio-corpo").replaceChildren(el("div", {}, [
    el("p", { class: "apoio" }, `${desafio.certidao} — ${desafio.titular}`),
    el("div", { class: "instrucao" }, desafio.instrucao),
    desafio.imagem
      ? el("div", { class: "captcha-caixa" }, el("img", { src: desafio.imagem, alt: "Imagem do captcha" }))
      : null,
    digitar ? entrada : null,
    restantes > 1
      ? el("p", { class: "apoio", style: "margin-top:10px" },
          `Responda e o próximo aparece na hora. ${restantes} pedido(s) na fila.`)
      : null,
  ]));

  $("#desafio-enviar").textContent = digitar
    ? (restantes > 1 ? "Enviar e próximo" : "Enviar")
    : "Já resolvi, pode continuar";
  $("#cortina-desafio").classList.remove("oculto");
  if (!mesmo || document.activeElement !== entrada) setTimeout(() => entrada.focus(), 30);

  $("#desafio-enviar").onclick = () => enviarResposta(digitar ? entrada.value.trim() : "ok");
  $("#desafio-adiar").onclick = () => {
    estado.desafiosAdiados.add(desafio.id);
    estado.desafios.shift();
    avisar("Pedido adiado. Ele continua aberto na aba Solicitações.");
    desenharSala();
  };
  $("#desafio-cancelar").onclick = async () => {
    const alvo = estado.desafios.shift();
    desenharSala();
    await api(`/api/solicitacoes/${alvo.solicitacao_id}/cancelar`, { method: "POST" });
    await carregar();
  };
}

async function enviarResposta(resposta) {
  const desafio = estado.desafios[0];
  if (!desafio) return;
  if (PRECISA_DIGITAR.has(desafio.tipo) && !resposta) {
    return avisar("Digite os caracteres da imagem.", "erro");
  }
  // Mostra o próximo imediatamente e envia em segundo plano: é isso que faz
  // 40 captchas virarem alguns minutos de digitação em vez de 40 esperas.
  estado.desafios.shift();
  desenharSala();
  try {
    await api(`/api/desafios/${desafio.id}/responder`, {
      method: "POST", body: JSON.stringify({ resposta }),
    });
  } catch {
    estado.desafios.unshift(desafio);
    desenharSala();
  }
}

/* ----------------------------------------------------------- configurações */
async function desenharConfiguracoes() {
  const preferencias = await api("/api/preferencias");
  const entrada = el("input", { type: "text", value: preferencias.padrao_nome_arquivo });
  const entradaEmail = el("input", {
    type: "email", value: preferencias.email_escritorio || "",
    placeholder: "contato@seuescritorio.adv.br",
  });
  const previa = el("code", {}, preferencias.exemplo);

  entrada.addEventListener("input", () => {
    previa.textContent = montarExemplo(entrada.value);
  });

  const salvar = el("button", { class: "botao primario" }, "Salvar padrão");
  salvar.addEventListener("click", async () => {
    const r = await api("/api/preferencias", {
      method: "PUT",
      body: JSON.stringify({
        padrao_nome_arquivo: entrada.value,
        email_escritorio: entradaEmail.value,
      }),
    });
    previa.textContent = r.exemplo;
    avisar("Configurações salvas. Valem para as próximas certidões.", "bom");
  });

  const campos = el("div", { class: "escolhas", style: "max-height:200px" },
    Object.entries(preferencias.campos).map(([campo, descricao]) =>
      el("div", { class: "escolha" }, [
        el("code", { style: "min-width:170px" }, `{${campo}}`),
        el("div", { class: "detalhe" }, descricao),
      ])
    )
  );

  const urlInspecao = el("input", { type: "text", placeholder: "https://site-do-orgao.gov.br/..." });
  const esperaInspecao = el("input", { type: "number", value: "0", min: "0", max: "300" });
  const resultado = el("div", {});
  const inspecionar = el("button", { class: "botao secundario" }, "Abrir e listar os campos");
  inspecionar.addEventListener("click", async () => {
    inspecionar.disabled = true;
    inspecionar.textContent = "Abrindo o site...";
    try {
      const r = await api("/api/inspecionar", {
        method: "POST",
        body: JSON.stringify({ url: urlInspecao.value, espera: Number(esperaInspecao.value) || 0 }),
      });
      resultado.replaceChildren(
        el("p", { class: "apoio" }, `${r.titulo || "(sem título)"} — ${r.campos.length} campo(s)`),
        el("table", {}, [
          el("thead", {}, el("tr", {}, ["Serve para", "Seletor", "Rótulo"].map((x) => el("th", {}, x)))),
          el("tbody", {}, r.campos.map((c) =>
            el("tr", {}, [
              el("td", {}, c.sugestao),
              el("td", {}, el("code", {}, c.seletor)),
              el("td", { class: "secundaria" }, c.rotulo || c.texto || c.alternativo || ""),
            ])
          )),
        ])
      );
    } finally {
      inspecionar.disabled = false;
      inspecionar.textContent = "Abrir e listar os campos";
    }
  });

  /* --- conferência das fontes contra os sites reais --- */
  const verNavegador = el("input", { type: "checkbox", checked: "checked" });
  const resultadoConferencia = el("div", {});
  const conferir = el("button", { class: "botao primario" }, "Conferir agora");
  conferir.addEventListener("click", async () => {
    conferir.disabled = true;
    conferir.textContent = "Conferindo nos sites dos órgãos...";
    resultadoConferencia.replaceChildren(
      el("p", { class: "apoio" }, "Isso leva um ou dois minutos. Nenhuma certidão é emitida.")
    );
    try {
      const relatorio = await api("/api/diagnostico", {
        method: "POST", body: JSON.stringify({ visivel: verNavegador.checked }),
      });
      desenharConferencia(relatorio, resultadoConferencia);
    } finally {
      conferir.disabled = false;
      conferir.textContent = "Conferir agora";
    }
  });

  /* --- credenciais de API contratada --- */
  const listaCredenciais = el("div", {});
  const rotuloCredencial = el("input", { type: "text", placeholder: "serpro_cnd" });
  const segredoCredencial = el("input", { type: "password", placeholder: "token fornecido no contrato" });

  async function desenharCredenciais() {
    const credenciais = await api("/api/credenciais");
    listaCredenciais.replaceChildren(
      credenciais.length
        ? el("table", {}, el("tbody", {}, credenciais.map((c) =>
            el("tr", {}, [
              el("td", {}, el("code", {}, c.rotulo)),
              el("td", { class: "secundaria" }, c.segredo || "—"),
              el("td", { class: "acoes" }, el("button", {
                class: "botao secundario miudo",
                onclick: async () => {
                  const certeza = await confirmar("Remover esta credencial?",
                    `As emissões que usam "${c.rotulo}" voltam a pedir o token.`, "Remover");
                  if (!certeza) return;
                  await api(`/api/credenciais/${encodeURIComponent(c.rotulo)}`, { method: "DELETE" });
                  await desenharCredenciais();
                },
              }, "Remover")),
            ])
          )))
        : el("p", { class: "apoio" }, "Nenhuma credencial cadastrada.")
    );
  }
  desenharCredenciais();

  const salvarCredencial = el("button", { class: "botao primario" }, "Guardar credencial");
  salvarCredencial.addEventListener("click", async () => {
    await api("/api/credenciais", {
      method: "PUT",
      body: JSON.stringify({ rotulo: rotuloCredencial.value, segredo: segredoCredencial.value }),
    });
    segredoCredencial.value = "";
    avisar("Credencial guardada, cifrada.", "bom");
    await desenharCredenciais();
  });

  /* --- custo das emissões pagas --- */
  const de = el("input", { type: "date" });
  const ate = el("input", { type: "date" });
  const resultadoCustos = el("div", {});
  const verCustos = el("button", { class: "botao secundario" }, "Ver custos");
  verCustos.addEventListener("click", async () => {
    const parametros = new URLSearchParams();
    if (de.value) parametros.set("de", de.value);
    if (ate.value) parametros.set("ate", ate.value);
    const r = await api(`/api/relatorios/custos?${parametros}`);
    resultadoCustos.replaceChildren(
      el("p", {}, `Total no período: R$ ${r.total.toFixed(2).replace(".", ",")}`),
      r.titulares.length
        ? el("table", {}, [
            el("thead", {}, el("tr", {}, ["Titular", "Emissões", "Custo"].map((x) => el("th", {}, x)))),
            el("tbody", {}, r.titulares.map((linha) =>
              el("tr", {}, [
                el("td", {}, [el("div", { class: "principal" }, linha.titular),
                              el("div", { class: "secundaria" }, linha.documento)]),
                el("td", {}, String(linha.emissoes)),
                el("td", {}, `R$ ${linha.total.toFixed(2).replace(".", ",")}`),
              ])
            )),
          ])
        : el("p", { class: "apoio" }, "Nenhuma emissão paga no período."),
      el("a", {
        class: "botao secundario miudo",
        href: `/api/relatorios/custos?${parametros}&formato=csv`,
        style: "text-decoration:none; display:inline-block; margin-top:10px",
      }, "Baixar planilha (CSV)"),
    );
  });

  $("#conteudo-configuracoes").replaceChildren(
    el("div", { class: "bloco" }, [
      el("div", { class: "bloco-cabecalho" }, el("h2", {}, "Credenciais de API")),
      el("div", { style: "padding:18px" }, [
        el("p", { class: "apoio" },
          "Algumas certidões podem ser emitidas por API contratada, sem captcha e sem bloqueio — " +
          "é o caso da CND Federal pela API do Serpro. O token fica guardado cifrado e nunca " +
          "é mostrado de volta."),
        listaCredenciais,
        el("div", { class: "linha", style: "margin-top:12px" }, [
          el("div", { class: "campo" }, [
            el("label", {}, ["Rótulo ", el("span", { class: "dica" }, "— o nome que a fonte espera")]),
            rotuloCredencial,
          ]),
          el("div", { class: "campo" }, [el("label", {}, "Token"), segredoCredencial]),
        ]),
        salvarCredencial,
      ]),
    ]),
    el("div", { class: "bloco" }, [
      el("div", { class: "bloco-cabecalho" }, el("h2", {}, "Custo das emissões")),
      el("div", { style: "padding:18px" }, [
        el("p", { class: "apoio" },
          "Emissões por API contratada são cobradas por consulta. Aqui está quanto cada titular " +
          "custou no período — é a base para repassar ao cliente."),
        el("div", { class: "linha" }, [
          el("div", { class: "campo" }, [el("label", {}, "De"), de]),
          el("div", { class: "campo" }, [el("label", {}, "Até"), ate]),
        ]),
        verCustos,
        resultadoCustos,
      ]),
    ]),
    el("div", { class: "bloco" }, [
      el("div", { class: "bloco-cabecalho" }, el("h2", {}, "Conferir as fontes")),
      el("div", { style: "padding:18px" }, [
        el("p", { class: "apoio" },
          "Percorre cada site de órgão e diz até onde a fonte ainda funciona. Não emite nada: " +
          "para antes do botão de emissão e antes de qualquer captcha. Rode depois de instalar e " +
          "sempre que uma emissão começar a falhar."),
        el("label", { class: "alternador", style: "margin:10px 0" },
          [verNavegador, "mostrar a janela do navegador (recomendado: alguns sites " +
           "entregam outra página para um navegador escondido)"]),
        conferir,
        resultadoConferencia,
      ]),
    ]),
    el("div", { class: "bloco" }, [
      el("div", { class: "bloco-cabecalho" }, el("h2", {}, "Nome dos arquivos")),
      el("div", { style: "padding:18px" }, [
        el("p", { class: "apoio" },
          "Todo PDF arquivado recebe este nome. Ele vai para a pasta do cliente e para o processo, então precisa se explicar sozinho."),
        el("div", { class: "campo" }, [el("label", {}, "Modelo"), entrada]),
        el("div", { class: "campo" }, [el("label", {}, "Fica assim"), el("div", { class: "registro" }, previa)]),
        el("div", { class: "campo" }, [el("label", {}, "Campos disponíveis"), campos]),
        el("div", { class: "campo" }, [
          el("label", {}, ["E-mail do escritório ",
            el("span", { class: "dica" },
              "— alguns órgãos mandam cópia da certidão por e-mail; em branco, vai para o e-mail do titular")]),
          entradaEmail,
        ]),
        salvar,
      ]),
    ]),
    el("div", { class: "bloco" }, [
      el("div", { class: "bloco-cabecalho" }, el("h2", {}, "Onde ficam os documentos")),
      el("div", { style: "padding:18px" }, [
        el("p", { class: "apoio" },
          "Os PDFs ficam organizados por titular e ano, com o nome padronizado acima. " +
          "Dá para consultá-los como qualquer outro arquivo, mesmo com o sistema fechado."),
        el("button", {
          class: "botao secundario",
          onclick: async (e) => {
            e.target.disabled = true;
            try {
              const r = await api("/api/abrir-pasta", { method: "POST" });
              avisar(`Pasta aberta: ${r.pasta}`, "bom");
            } finally { e.target.disabled = false; }
          },
        }, "Abrir a pasta dos documentos"),
      ]),
    ]),
    el("div", { class: "bloco" }, [
      el("div", { class: "bloco-cabecalho" }, el("h2", {}, "Mapear um site novo")),
      el("div", { style: "padding:18px" }, [
        el("p", { class: "apoio" },
          "Abre o site do órgão e lista os campos com o seletor de cada um — é o que permite acrescentar o seu tribunal, a SEFAZ ou a prefeitura sem ler código."),
        el("div", { class: "campo" }, [el("label", {}, "Endereço"), urlInspecao]),
        el("div", { class: "campo" }, [
          el("label", {}, ["Esperar quantos segundos antes de capturar ",
            el("span", { class: "dica" }, "para você navegar até a tela certa")]),
          esperaInspecao,
        ]),
        inspecionar,
        resultado,
      ]),
    ])
  );
}

const SELO_CONFERENCIA = {
  pronta: ["vigente", "A fonte está de pé"],
  parcial: ["vence_em_breve", "Atenção"],
  quebrada: ["vencida", "Precisa de ajuste"],
};

function desenharConferencia(relatorio, destino) {
  const cartoes = relatorio.fontes.map((fonte) => {
    const [classe, rotulo] = SELO_CONFERENCIA[fonte.situacao] || ["ausente", fonte.situacao];
    const passos = (fonte.passos || []).map((passo) => {
      const marca = { ok: "✓", pulado: "–", nao_encontrado: "✗", erro: "✗" }[passo.resultado] || "?";
      return el("div", { class: "secundaria" },
        `${marca} ${passo.acao} ${passo.seletor || ""}${passo.detalhe ? " — " + passo.detalhe : ""}`);
    });
    const campos = (fonte.campos_da_pagina || []).length
      ? el("details", { style: "margin-top:10px" }, [
          el("summary", { class: "secundaria" },
            `Campos que a página tem hoje (${fonte.campos_da_pagina.length})`),
          el("table", {}, el("tbody", {}, fonte.campos_da_pagina.slice(0, 40).map((campo) =>
            el("tr", {}, [
              el("td", {}, campo.sugestao),
              el("td", { class: "secundaria" },
                campo.marcador + (campo.tipo ? `[${campo.tipo}]` : "")),
              el("td", {}, el("code", {}, campo.seletor)),
              el("td", { class: "secundaria" }, campo.rotulo || campo.texto || campo.alternativo || ""),
            ])
          ))),
        ])
      : null;
    return el("div", { style: "border-top:1px solid var(--borda); padding:14px 0" }, [
      el("div", {}, [
        el("span", { class: `pilula ${classe}` }, rotulo),
        el("strong", { style: "margin-left:8px" }, fonte.nome),
      ]),
      el("p", { class: "apoio", style: "margin:6px 0" }, fonte.mensagem),
      ...passos,
      campos,
      fonte.captura
        ? el("details", {}, [
            el("summary", { class: "secundaria" }, "Ver a tela no momento da falha"),
            el("img", { src: fonte.captura, style: "max-width:100%; border:1px solid var(--borda); border-radius:6px; margin-top:8px" }),
          ])
        : null,
    ]);
  });

  const quebradas = relatorio.fontes.filter((r) => r.situacao === "quebrada").length;
  destino.replaceChildren(
    el("p", { style: "margin-top:16px" },
      quebradas
        ? `${quebradas} fonte(s) precisam de ajuste. Baixe o relatório e envie para quem cuida do sistema.`
        : "Todas as fontes conferidas estão de pé."),
    el("a", {
      class: "botao secundario", href: "/api/diagnostico/relatorio",
      style: "text-decoration:none; display:inline-block; margin-bottom:8px",
    }, "Baixar relatório"),
    ...cartoes,
  );
}

function montarExemplo(padrao) {
  const valores = {
    sigla: "CNDT", codigo: "cndt",
    certidao: "Certidao-Negativa-de-Debitos-Trabalhistas",
    orgao: "Tribunal-Superior-do-Trabalho",
    nome: "Construtora-Horizonte-Ltda",
    documento: "11222333000181", documento_formatado: "11.222.333-0001-81",
    emissao: "2026-08-27", validade: "2027-02-22",
    emissao_br: "27-08-2026", validade_br: "22-02-2027",
    ano: "2026", numero: "12345678-2026",
  };
  let nome = padrao || "";
  for (const [campo, valor] of Object.entries(valores)) nome = nome.split(`{${campo}}`).join(valor);
  nome = nome.replace(/\{[a-z_]+\}/g, "").replace(/-{2,}/g, "-").replace(/^[-._]+|[-._]+$/g, "");
  return `${nome || "certidao"}.pdf`;
}

/* -------------------------------------------------------------- navegação */
const TITULOS = {
  painel: ["Painel", "O que está vigente, o que vence e o que falta emitir."],
  titulares: ["Titulares", "Pessoas e empresas acompanhadas pelo escritório."],
  solicitacoes: ["Solicitações", "A fila de emissões e o histórico de tentativas."],
  acervo: ["Acervo", "Todos os documentos arquivados, com o PDF original."],
  catalogo: ["Catálogo", "Como cada certidão é obtida e por quanto tempo vale."],
  configuracoes: ["Configurações", "Padrão de nome dos arquivos e mapeamento de sites novos."],
};

function irPara(pagina) {
  estado.pagina = pagina;
  location.hash = pagina;
  for (const secao of document.querySelectorAll(".pagina")) secao.classList.add("oculto");
  $(`#pagina-${pagina}`).classList.remove("oculto");
  for (const link of document.querySelectorAll("#navegacao a")) {
    link.classList.toggle("ativo", link.dataset.pagina === pagina);
  }
  const [titulo, subtitulo] = TITULOS[pagina];
  $("#titulo-pagina").textContent = titulo;
  $("#subtitulo-pagina").textContent = subtitulo;
  $("#botao-emitir-pendentes").classList.toggle("oculto", pagina !== "painel");
  if (pagina === "solicitacoes") desenharSolicitacoes();
  if (pagina === "acervo") desenharAcervo();
  if (pagina === "configuracoes") desenharConfiguracoes();
}

/* ------------------------------------------------------------------ carga */
async function carregar() {
  const [resumo, painel, titulares, tipos] = await Promise.all([
    api("/api/resumo"), api("/api/painel"), api("/api/titulares"), api("/api/tipos"),
  ]);
  Object.assign(estado, { resumo, painel, titulares, tipos });
  desenharCartoes();
  desenharPainel();
  desenharTitulares();
  desenharCatalogo();
  desenharSolicitacoes();  // também atualiza o contador da barra lateral
  if (estado.pagina === "acervo") desenharAcervo();

  const aviso = $("#aviso-modo");
  aviso.classList.toggle("oculto", !resumo.modo_demonstracao);
  if (resumo.modo_demonstracao) {
    aviso.textContent = "Modo demonstração: os documentos gerados são fictícios e não têm valor legal.";
  }
}

function ajuda() {
  abrirModal("Como funciona", el("div", {}, [
    el("p", {}, "1. Cadastre o titular (pessoa ou empresa) e marque quais certidões ele precisa manter vigentes."),
    el("p", {}, "2. O painel mostra o que está vigente, o que vence em breve e o que falta. O sistema renova sozinho quando o vencimento se aproxima."),
    el("p", {}, "3. Quando o site do órgão pedir um captcha ou o login gov.br, a tela avisa e mostra o que fazer — quem responde é você, o sistema só conduz o resto."),
    el("p", {}, "4. Onde não há automação, o sistema abre o site certo e arquiva o PDF que você anexar, mantendo o controle de validade igual."),
    el("p", { class: "apoio" }, "Os PDFs ficam na pasta de documentos do sistema, organizados por titular e ano — dá para consultar mesmo sem abrir o programa."),
  ]), [el("button", { class: "botao secundario", onclick: fecharModal }, "Fechar")]);
}

/* -------------------------------------------------------------------- início */
document.addEventListener("DOMContentLoaded", () => {
  for (const link of document.querySelectorAll("#navegacao a")) {
    link.addEventListener("click", (e) => { e.preventDefault(); irPara(link.dataset.pagina); });
  }
  $("#modal-fechar").addEventListener("click", fecharModal);
  $("#cortina").addEventListener("click", (e) => { if (e.target.id === "cortina") fecharModal(); });
  $("#botao-atualizar").addEventListener("click", () => carregar().then(() => avisar("Atualizado.")));
  $("#botao-novo-titular").addEventListener("click", () => formularioTitular());
  $("#botao-ajuda").addEventListener("click", ajuda);
  $("#incluir-substituidas").addEventListener("change", desenharAcervo);
  $("#botao-limpar-solicitacoes").addEventListener("click", async () => {
    const certeza = await confirmar("Limpar as solicitações encerradas?",
      "Some da lista tudo o que falhou ou foi cancelado. As certidões arquivadas não são tocadas.",
      "Limpar");
    if (!certeza) return;
    const r = await api("/api/solicitacoes/limpar", { method: "POST" });
    avisar(r.removidas ? `${r.removidas} solicitação(ões) removidas.` : "Nada a limpar.", "bom");
    await carregar();
  });
  $("#botao-emitir-pendentes").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      const r = await api("/api/solicitacoes/pendentes", { method: "POST" });
      avisar(r.criadas ? `${r.criadas} emissão(ões) na fila.` : "Nada pendente no momento.", r.criadas ? "bom" : "");
      await carregar();
    } finally { e.target.disabled = false; }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") fecharModal(); });

  irPara(location.hash.slice(1) || "painel");
  carregar();
  setInterval(atualizarDesafios, 1500);
  setInterval(() => { if (!$("#cortina").classList.contains("oculto")) return; carregar(); }, 15000);
});
