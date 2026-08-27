# Certidões — gestão e emissão automatizada

Sistema para escritórios que precisam **manter certidões públicas sempre vigentes**:
controla validade, avisa antes de vencer, renova sozinho o que dá para renovar e
conduz o usuário no que ainda exige uma pessoa (captcha, login gov.br, sites sem
automação). Tudo roda na máquina do escritório, com painel no navegador — sem
comando de terminal para o uso do dia a dia.

## Começar

1. Instale o Python 3.10 ou mais novo ([python.org](https://www.python.org/downloads/) —
   no Windows, marque *Add Python to PATH* na instalação).
2. Dê dois cliques em **`iniciar.bat`** (Windows) ou **`iniciar.command`** (macOS/Linux).
   Na primeira vez ele instala o que falta; depois abre o painel sozinho no navegador.
3. Para a automação em navegador, uma vez só, instale o Chromium do Playwright:

   ```
   python -m playwright install chromium
   ```

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

### Validade: o documento manda

`validade_dias` do catálogo é só o padrão do órgão. Quando o PDF informa a data de
validade, é a data do PDF que vale — é ela que o fiscal vai olhar.

## Automação, sem fingimento

Cada órgão vira uma **receita** declarativa (`certidoes/receitas/*.yaml`), executada
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
`exigir_texto`, `aguardar_download`, `salvar_pagina_pdf`.

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

**2. Login uma vez, muitas emissões.** Uma receita pode declarar `perfil: govbr`.
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

### Quando o site muda

Uma receita pode declarar `ao_falhar: pedir_anexo`. Se um passo não encontra o
que esperava, em vez de falhar o sistema deixa o navegador aberto **na página
certa**, avisa que o site mudou e pede o PDF. Você conclui à mão e o arquivo é
arquivado normalmente — a receita desatualizada vira um contratempo, não um beco
sem saída.

Onde não há automação (ou ela ainda não foi validada), o sistema **abre o site
certo** e pede o PDF: o arquivo anexado é arquivado, lido e passa a ser controlado
como qualquer outro — o controle de validade nunca depende da automação existir.

### O que já está pronto, e o que ainda não

| Certidão | Situação |
|---|---|
| **CNDT** (TST) | Receita completa com captcha de imagem, paralelizável. Seletores conferidos contra o site em 27/08/2026. |
| **CRF/FGTS** (Caixa) | Receita completa (CNPJ ou CPF + UF), sem captcha na consulta. Seletores conferidos em 27/08/2026. |
| **CND Federal** (RFB/PGFN) | Receita escrita para o portal atual (`servicos.receitafederal.gov.br`), com `captcha_interativo`: a API recusa a emissão sem o token do hCaptcha, então o widget é resolvido por você na janela e o resto é automático. Seletores ainda não conferidos. |
| **Certidão Unificada da Justiça Federal** (CJF) | Receita escrita para `certidao-unificada.cjf.jus.br`. Cobre as Regiões **exceto o TRF6**, que segue fora do sistema unificado — para a 6ª Região, emita à parte. Seletores ainda não conferidos: o site recusa conexões de fora de uma rede comum. |
| **Estaduais e municipais** | Cadastradas como modelo no catálogo, sem receita: use **Configurações › Mapear um site novo** para descobrir os campos do seu tribunal/SEFAZ/prefeitura. |

Honestidade sobre o estado atual: **as receitas da CNDT e do FGTS foram escritas a
partir dos formulários reais**, e o motor de navegador é testado de ponta a ponta
(preencher, ler captcha, receber recusa, repetir, baixar o PDF) contra uma réplica
local dos portais. As da Receita e do CJF foram escritas sem poder abrir as
páginas — a primeira é um aplicativo Angular protegido por hCaptcha, a segunda
recusa conexões de fora de uma rede comum. As quatro precisam de uma execução real
na sua máquina; as duas últimas, de um ajuste de seletores. Por isso todas
declaram `ao_falhar: pedir_anexo`: mesmo antes do acerto fino, o pior caso é você
concluir na janela já aberta na página certa. Cada tipo mostra no Catálogo a data
em que sua receita foi conferida.

### Mapear um site novo, sem programar

**Configurações › Mapear um site novo** abre o endereço que você informar, espera
o tempo que você pedir (para navegar até a tela certa, inclusive passando por um
login) e lista cada campo da página com o seletor pronto e um palpite do que ele
serve — "preencher (documento)", "clicar", "captcha_imagem", "captcha_interativo".
É com essa lista que se completa a receita de um tribunal ou de uma prefeitura.
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
  catalogo/       catálogo de certidões (YAML)
  receitas/       uma receita por órgão (YAML)
  automacao/      motor de navegador, simulador, captcha, inspeção e leitura do PDF
  api/            FastAPI
  web/            painel (HTML/CSS/JS, sem build)
testes/           inclui uma réplica local de portal para testar o navegador
```

## Próximos passos naturais

1. Rodar as quatro receitas contra os sites de produção, ajustar os seletores da
   Receita e do CJF com o mapeador e marcar a data de conferência.
2. Mapear o TJ estadual de maior volume no escritório e a SEFAZ da UF principal.
3. Aviso por e-mail dos vencimentos (hoje o alerta é o painel).
4. Exportar o "dossiê de habilitação": um PDF único com todas as certidões vigentes
   de um titular — é o que a licitação pede.
5. Login de usuários, se o sistema for atender mais de um escritório.
