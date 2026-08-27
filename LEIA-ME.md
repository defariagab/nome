# Certidões — gestão e emissão automatizada

Sistema para escritórios que precisam **manter certidões públicas sempre vigentes**:
controla validade, avisa antes de vencer, renova sozinho o que dá para renovar e
conduz o usuário no que ainda exige uma pessoa (captcha, login gov.br, sites sem
automação). Tudo roda na máquina do escritório, com painel no navegador — sem
comando de terminal para o uso do dia a dia.

## Começar

Se você não programa, siga o **[COMECE-AQUI.md](COMECE-AQUI.md)** — são quatro passos.

Resumindo: instale o Python 3.10 ou mais novo e dê dois cliques em **`iniciar.bat`**
(Windows) ou **`iniciar.command`** (macOS/Linux). Na primeira vez ele instala as
bibliotecas **e o navegador do Playwright** sozinho, e depois abre o painel. Se o
navegador não puder ser instalado, o sistema abre assim mesmo: o controle de
validade e o arquivo de PDFs não dependem dele.

Quer conhecer o sistema antes de cadastrar clientes de verdade?

```
python -m certidoes demonstracao     # cria um escritório fictício com casos variados
```

Com `CERTIDOES_MOTOR=simulador` nada sai da máquina: as certidões são geradas
localmente, marcadas como **sem valor legal**, e servem para treinar a equipe.

## Como o sistema pensa

| Conceito | O que é |
|---|---|
| **Titular** | A pessoa ou empresa para quem as certidões são emitidas. |
| **Tipo de certidão** | Cada espécie do catálogo (CNDT, CRF/FGTS, CND Federal...), com órgão, validade padrão, se exige gov.br e que captcha usa. |
| **Monitoramento** | "Este titular precisa manter esta certidão vigente" — é isso que faz a certidão aparecer no painel e ser renovada. |
| **Solicitação** | Uma tentativa de obter a certidão. Vive numa fila e conta o que aconteceu. |
| **Certidão** | O documento emitido e arquivado, com número, validade e o PDF original. |

O painel classifica cada linha em **vigente**, **vence em breve**, **vencida**,
**não emitida** ou **positiva (com débitos)** — e ordena pela urgência, não pelo
nome. Certidão positiva não entra em renovação automática: reemitir não resolve
débito, e o sistema não finge que resolve.

### Nome dos arquivos

Todo PDF arquivado recebe um nome segundo o padrão do escritório, definido em
**Configurações › Nome dos arquivos** com prévia ao vivo. O padrão de fábrica:

```
CNDT_Construtora-Horizonte-Ltda_11222333000181_valida-ate-2027-02-22.pdf
```

Campos disponíveis: `{sigla}`, `{codigo}`, `{certidao}`, `{orgao}`, `{nome}`,
`{documento}`, `{documento_formatado}`, `{emissao}`, `{validade}`, `{emissao_br}`,
`{validade_br}`, `{ano}`, `{numero}`. O sistema recusa modelos que não
identifiquem o titular ou não diferenciem as versões, tira acentos e caracteres
proibidos, corta nomes longos demais e nunca deixa uma certidão sobrescrever
outra de conteúdo diferente. Os arquivos continuam organizados em pastas por
titular e ano.

### E-mail do escritório

Alguns órgãos mandam cópia da certidão por e-mail — o CJF é um deles. Em
**Configurações**, o *E-mail do escritório* define para onde essa cópia vai:
por padrão, para quem acompanha o vencimento, e não para o cliente. Em branco,
usa o e-mail do titular. Nas fontes, é a variável `{email_notificacao}`.

### Validade: o documento manda

`validade_dias` do catálogo é só o padrão do órgão. Quando o PDF informa a data de
validade, é a data do PDF que vale — é ela que o fiscal vai olhar.

## Automação, sem fingimento

Cada órgão vira uma **fonte** declarativa (`certidoes/fontes/*.yaml`), executada
por um navegador real:

```yaml
passos:
  - acao: abrir
    url: "{url}"
  - acao: preencher
    seletor: "[id='gerarCertidaoForm:cpfCnpj']"
    valor: "{documento_formatado}"
  - acao: captcha_imagem
    seletor: "#idImgBase64"
    campo: "#idCampoResposta"
  - acao: clicar
    seletor: "[id='gerarCertidaoForm:btnEmitirCertidao']"
  - acao: aguardar_download
    timeout: 90
```

Passos disponíveis: `abrir`, `preencher`, `selecionar`, `clicar`, `esperar`,
`captcha_imagem`, `login_gov_br`, `acao_manual`, `exigir_texto`,
`aguardar_download`, `salvar_pagina_pdf`. Variáveis: `{documento}`,
`{documento_formatado}`, `{nome}`, `{uf}`, `{municipio}`, `{email}`,
`{inscricao_estadual}`, `{url}` e outras (veja `servicos.variaveis_do_contexto`).

Passos disponíveis: `abrir`, `preencher`, `selecionar`, `clicar`, `esperar`,
`captcha_imagem`, `captcha_interativo`, `login_gov_br`, `acao_manual`,
`abrir_no_navegador`, `exigir_texto`, `aguardar_download`, `salvar_pagina_pdf`.

Dois modificadores servem para os sites do mundo real:

- **`quando:`** liga o passo a uma variável. `quando: cnpj` roda só para pessoa
  jurídica, `quando: "!cnpj"` só para física — é o que resolve os sites que
  separam CPF e CNPJ em campos diferentes, como o do CJF.
- **`opcional: true`** deixa o passo passar quando o elemento não está lá.
  Banner de cookies, aviso de manutenção, campo que só aparece às vezes.

### Captcha em escala: o problema dos 40 captchas

Emitir 40 certidões não pode custar 40 interrupções. Três mecanismos atacam isso:

**1. Sala de captchas.** As emissões com captcha de letras rodam **em paralelo**
(quatro por vez, ajustável). As imagens chegam a uma única tela, uma atrás da
outra: você digita, tecla Enter e a próxima já está lá — sem esperar cada site
carregar, sem trocar de janela. Quarenta captchas viram alguns minutos de
digitação em vez de quarenta esperas. Quem responde continua sendo uma pessoa: o
sistema não quebra, não contorna e não terceiriza captcha, porque esse controle
existe justamente para exigir presença humana, e burlá-lo em sistema público não
é caminho que este projeto siga.

**2. Login uma vez, muitas emissões.** Uma fonte pode declarar `perfil: govbr`.
O navegador guarda a sessão daquele perfil: você entra no gov.br **uma vez** e as
emissões seguintes reaproveitam o login, sem novo captcha e sem nova senha. O
passo `login_gov_br` ainda aceita `sinal_logado` — um seletor que só existe na
página quando a sessão está ativa — e nem chega a incomodar você quando já está.

**3. Não emitir o que não precisa.** Certidão vigente não é reemitida; certidão
positiva não entra em renovação automática; e a renovação dispara por
antecedência, espalhando o trabalho em vez de acumular tudo no mesmo dia.

Onde o captcha é um widget interativo (hCaptcha, reCAPTCHA — o caso do portal
novo da Receita), não há imagem para recortar: o passo `captcha_interativo` traz
a janela do navegador para a frente, você resolve ali e confirma no painel. Essas
emissões rodam **uma de cada vez**, porque ninguém opera quatro janelas ao mesmo
tempo — e, enquanto uma delas espera por você, as de captcha de letras continuam
rodando normalmente.

### Quando o órgão recusa automação

Alguns portais barram navegador automatizado. O da Receita Federal responde
exatamente isto: *"o seu acesso foi bloqueado por possuir atributos que o
caracteriza como um acesso automatizado"*.

Esse bloqueio existe de propósito, e o sistema **não tenta se disfarçar para
passar por ele**. A fonte usa então o passo `abrir_no_navegador`: o endereço
abre no navegador que a pessoa já usa — onde a sessão gov.br normalmente já está
ativa — e o sistema segue cuidando de tudo o que vem depois: arquivamento, nome
padronizado, leitura da validade no PDF, controle de vencimento, dossiê.

Fontes assim nem abrem o navegador do sistema: não há por que abrir uma janela
que o órgão vai recusar.

### Página de erro não vira certidão

Órgãos respondem com página de erro, aviso de instabilidade e tela de manutenção
— tudo com status 200 e aparência de resposta normal. Arquivar isso como certidão
é pior do que falhar: o painel fica verde, o dossiê leva a página errada e o
problema só aparece na mesa do fiscal.

Todo documento — emitido pela automação ou anexado à mão — passa por uma
conferência antes de entrar no acervo. Ele é recusado quando traz aviso de
indisponibilidade ("não foi possível verificar", "tente novamente mais tarde",
"em manutenção", "acesso bloqueado") ou quando não traz nada que o identifique
como certidão: nem situação, nem validade, nem número. A solicitação falha com o
motivo em português, e a renovação automática tenta de novo mais tarde.

Isto veio de um caso real: a Caixa respondeu com a página "Situação de
Regularidade do Empregador" dizendo que **não** conseguiu verificar a
regularidade, e a versão anterior arquivou como certificado válido — bastava a
palavra "Regularidade" aparecer. Hoje um teste guarda esse documento exato.

### Quando o site muda

Uma fonte pode declarar `ao_falhar: pedir_anexo`. Se um passo não encontra o
que esperava, em vez de falhar o sistema deixa o navegador aberto **na página
certa**, avisa que o site mudou e pede o PDF. Você conclui à mão e o arquivo é
arquivado normalmente — a fonte desatualizada vira um contratempo, não um beco
sem saída.

Onde não há automação (ou ela ainda não foi validada), o sistema **abre o site
certo** e pede o PDF: o arquivo anexado é arquivado, lido e passa a ser controlado
como qualquer outro — o controle de validade nunca depende da automação existir.

### O que já está pronto, e o que ainda não

| Certidão | Situação |
|---|---|
| **CNDT** (TST) | **Conferida no escritório em 27/08/2026**: caminho inteiro reconhecido, do início ao captcha. |
| **CRF/FGTS** (Caixa) | **Conferida no escritório em 27/08/2026**: caminho inteiro reconhecido, até o botão de emissão. |
| **CND Federal** (RFB/PGFN) | O portal **recusa navegador automatizado**, e o sistema não contorna isso: abre o endereço no navegador do usuário e arquiva o PDF anexado, com controle de validade igual ao das demais. |
| **Certidão Unificada da Justiça Federal** (CJF) | Campos conferidos em 27/08/2026: CPF e CNPJ ficam em campos separados (daí o `quando:`), e o site usa reCAPTCHA. Emite na hora e ainda manda cópia por e-mail. Cobre as Regiões **exceto o TRF6**. |
| **Estaduais e municipais** | Cadastradas como modelo no catálogo, sem fonte: use **Configurações › Mapear um site novo** para descobrir os campos do seu tribunal/SEFAZ/prefeitura. |

Honestidade sobre o estado atual: **as fontes da CNDT e do FGTS foram escritas a
partir dos formulários reais**, e o motor de navegador é testado de ponta a ponta
(preencher, ler captcha, receber recusa, repetir, baixar o PDF) contra uma réplica
local dos portais. As da Receita e do CJF foram escritas sem poder abrir as
páginas — a primeira é um aplicativo Angular protegido por hCaptcha, a segunda
recusa conexões de fora de uma rede comum. As quatro precisam de uma execução real
na sua máquina; as duas últimas, de um ajuste de seletores. Por isso todas
declaram `ao_falhar: pedir_anexo`: mesmo antes do acerto fino, o pior caso é você
concluir na janela já aberta na página certa. Cada tipo mostra no Catálogo a data
em que sua fonte foi conferida.

### Conferir se as fontes ainda funcionam

**Configurações › Conferir as fontes** percorre cada site de órgão e diz até onde
a fonte ainda funciona — **sem emitir nada**: para antes do botão de emissão e
antes de qualquer captcha. Quando um campo não é achado, o relatório traz a lista
dos campos que a página tem hoje, com o seletor de cada um, mais uma captura da
tela: é o suficiente para corrigir a fonte sem abrir o site de novo. O relatório
fica em `.certidoes/diagnostico/` em duas versões (JSON e texto), para enviar a
quem for consertar. Pela linha de comando:

```
python -m certidoes conferir           # --ver mostra a janela do navegador
```

Os dados usados na conferência são fictícios: nenhum documento de cliente entra no
relatório. Ela roda com a **janela do navegador visível** por padrão, de propósito:
alguns sites entregam outra página para um navegador escondido, e uma conferência
que não reproduz as condições reais dá resposta enganosa.

O relatório também informa **com qual elemento cada seletor casou** e avisa quando
um seletor casa com vários — foi assim que se descobriu que um seletor largo demais
preenchia a caixa de busca do portal da Receita em vez do campo da certidão.

### Dossiê de regularidade

O botão **Dossiê**, na lista de titulares, gera um PDF único com todas as certidões
vigentes daquele titular, com folha de rosto listando órgão, número e validade de
cada uma. Certidão vencida ou positiva fica de fora, e de cada tipo entra só a mais
recente — é o documento que a habilitação de uma licitação pede.

### Mapear um site novo, sem programar

**Configurações › Mapear um site novo** abre o endereço que você informar, espera
o tempo que você pedir (para navegar até a tela certa, inclusive passando por um
login) e lista cada campo da página com o seletor pronto e um palpite do que ele
serve — "preencher (documento)", "clicar", "captcha_imagem", "captcha_interativo".
É com essa lista que se completa a fonte de um tribunal ou de uma prefeitura.
Pela linha de comando, o mesmo:

```
python -m certidoes inspecionar https://site-do-orgao.gov.br --espera 30
```

## Segurança e dados

- Tudo fica em `~/.certidoes` (ou na pasta de `CERTIDOES_DADOS`): banco SQLite,
  PDFs organizados por titular e ano, sessões de navegador. Backup = copiar a pasta.
- Senhas e credenciais gov.br são gravadas **cifradas** (Fernet/AES); a chave fica
  num arquivo separado com permissão 0600. Um segredo nunca volta pela API.
- O servidor escuta só em `127.0.0.1`. Ele não foi feito para ser exposto na
  internet como está: publicar exige autenticação de usuários antes.
- Você trata dados pessoais de terceiros (LGPD). O sistema guarda a trilha de
  auditoria de tudo que faz, e titulares são **desativados**, nunca apagados, para
  preservar o acervo probatório.

## Rodando os testes

```
python -m pytest              # tudo, menos o navegador
python -m pytest -m integracao  # motor de navegador contra a réplica local
```

Os testes de navegador pulam sozinhos se o Chromium do Playwright não estiver
instalado.

## Configuração

| Variável | Para quê |
|---|---|
| `CERTIDOES_DADOS` | Pasta de dados (padrão `~/.certidoes`). |
| `CERTIDOES_PORTA` | Porta do painel (padrão 8765). |
| `CERTIDOES_MOTOR` | `navegador` (padrão) ou `simulador`. |
| `CERTIDOES_NAVEGADOR_VISIVEL` | `0` esconde a janela do navegador. |
| `CERTIDOES_CHROMIUM` | Caminho de um Chrome/Chromium já instalado. |
| `CERTIDOES_PROXY` | Proxy corporativo, se houver. |
| `CERTIDOES_PARALELISMO` | Quantas emissões de captcha de letras rodam juntas (padrão 4). |

Comandos de manutenção (úteis para agendar no Windows/cron):

```
python -m certidoes renovar        # verifica vencimentos e enfileira renovações
python -m certidoes catalogo       # recarrega o catálogo de tipos
```

## Estrutura

```
certidoes/
  modelos.py      banco de dados (titular, tipo, monitoramento, certidão, solicitação...)
  validade.py     regras de vigência — o coração da gestão
  servicos.py     regras de aplicação usadas pela API
  fila.py         executa as solicitações, uma a uma
  agenda.py       renovação automática antes do vencimento
  nomeacao.py     padrão de nome dos PDFs arquivados
  diagnostico.py  conferência das fontes contra os sites reais
  dossie.py       PDF único com as certidões vigentes de um titular
  catalogo/       catálogo de certidões (YAML)
  fontes/       uma fonte por órgão (YAML)
  automacao/      motor de navegador, simulador, captcha, inspeção e leitura do PDF
  api/            FastAPI
  web/            painel (HTML/CSS/JS, sem build)
testes/           inclui uma réplica local de portal para testar o navegador
```

## Próximos passos naturais

1. Rodar **Configurações › Conferir as fontes** na máquina do escritório e
   ajustar os seletores da Receita e do CJF com o relatório gerado.
2. Mapear o TJ estadual de maior volume no escritório e a SEFAZ da UF principal.
3. Aviso por e-mail dos vencimentos (hoje o alerta é o painel).
4. Exportar o "dossiê de habilitação": um PDF único com todas as certidões vigentes
   de um titular — é o que a licitação pede.
5. Login de usuários, se o sistema for atender mais de um escritório.
