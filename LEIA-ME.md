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

**O captcha é respondido por uma pessoa.** O sistema recorta a imagem da tela do
órgão, mostra no painel, recebe o que o usuário digitou e devolve ao site — nada é
quebrado, contornado ou terceirizado. Se o site recusar a resposta, ele refaz o
caminho com uma imagem nova, até três vezes. O login gov.br funciona igual: a
janela do navegador abre, a pessoa autentica, e a sessão fica guardada para as
próximas emissões daquele titular.

Onde não há automação (ou ela ainda não foi validada), o sistema **abre o site
certo** e pede o PDF: o arquivo anexado é arquivado, lido e passa a ser controlado
como qualquer outro — o controle de validade nunca depende da automação existir.

### O que já está pronto, e o que ainda não

| Certidão | Situação |
|---|---|
| **CNDT** (TST) | Receita completa com captcha de imagem. Seletores conferidos contra o site em 27/08/2026. |
| **CRF/FGTS** (Caixa) | Receita completa (CNPJ ou CPF + UF), sem captcha na consulta. Seletores conferidos em 27/08/2026. |
| **CND Federal** (RFB/PGFN) | Modo assistido: o sistema abre o portal e arquiva o PDF que você anexar. O endereço direto de emissão muda com frequência e ainda não foi validado. |
| **Justiça Federal** (TRF) | Modo assistido, com a URL configurável por Região. Vários tribunais bloqueiam acesso automatizado. |
| **Estaduais e municipais** | Cadastradas como modelo no catálogo, sem receita: configure a URL do seu tribunal/SEFAZ/prefeitura na aba Catálogo. |

Honestidade sobre o estado atual: **as receitas da CNDT e do FGTS foram escritas a
partir dos formulários reais**, e o motor de navegador é testado de ponta a ponta
(preencher, ler captcha, receber recusa, repetir, baixar o PDF) contra uma réplica
local dos portais. O que ainda falta é rodar essas duas receitas contra os sites de
produção na sua máquina, com um CNPJ real — é a primeira coisa a fazer depois de
instalar. Sites de órgão mudam; por isso cada tipo mostra no Catálogo a data em que
sua receita foi conferida.

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
  catalogo/       catálogo de certidões (YAML)
  receitas/       uma receita por órgão (YAML)
  automacao/      motor de navegador, simulador, captcha e leitura do PDF
  api/            FastAPI
  web/            painel (HTML/CSS/JS, sem build)
testes/           inclui uma réplica local de portal para testar o navegador
```

## Próximos passos naturais

1. Validar CNDT e FGTS contra os sites de produção e marcar a data de conferência.
2. Mapear a CND Federal e um TJ estadual (o de maior volume no escritório).
3. Aviso por e-mail dos vencimentos (hoje o alerta é o painel).
4. Exportar o "dossiê de habilitação": um PDF único com todas as certidões vigentes
   de um titular — é o que a licitação pede.
5. Login de usuários, se o sistema for atender mais de um escritório.
