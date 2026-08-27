"""Execução das fontes em um navegador real (Playwright/Chromium).

Sites de órgãos públicos são, na prática, aplicações JSF cheias de AJAX,
sessão e captcha. Conduzir um navegador de verdade é mais confiável do que
tentar reproduzir as requisições — e é o que permite entregar a imagem do
captcha ao usuário e seguir de onde parou depois da resposta dele.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import date

import webbrowser

from ..config import config
from ..modelos import SituacaoCertidao, TipoDesafio
from .extracao import analisar
from .tipos import Contexto, ErroAutomacao, Fonte, Resultado

#: trechos que a mensagem do Playwright traz quando o Chromium não foi baixado
SINAIS_SEM_NAVEGADOR = ("executable doesn't exist", "playwright install", "please run the following")

SEM_NAVEGADOR = (
    "O navegador que conversa com os sites dos órgãos não está instalado. "
    "Feche o sistema e abra de novo pelo iniciar.bat (Windows) ou iniciar.command "
    "(Mac): ele baixa o navegador sozinho. Enquanto isso, o controle de validade e "
    "o arquivo de PDFs continuam funcionando normalmente."
)


def _erro_de_navegador(erro: Exception) -> ErroAutomacao | None:
    """Traduz falhas de infraestrutura em algo que o usuário possa resolver."""
    texto = str(erro).lower()
    if any(sinal in texto for sinal in SINAIS_SEM_NAVEGADOR):
        return ErroAutomacao(SEM_NAVEGADOR)
    if "err_internet_disconnected" in texto or "err_name_not_resolved" in texto:
        return ErroAutomacao(
            "Não há conexão com a internet, ou o endereço do órgão não foi encontrado."
        )
    if "err_connection" in texto or "err_timed_out" in texto:
        return ErroAutomacao(
            "Não consegui alcançar o site do órgão. Ele pode estar fora do ar ou bloqueando "
            "o acesso desta rede. Tente novamente mais tarde."
        )
    return None


class Navegador:
    """Envolve o Playwright e mantém a sessão (cookies, login gov.br)."""

    def __init__(self, *, visivel: bool = True, pasta_sessao: str | None = None):
        self.visivel = visivel
        self.pasta_sessao = pasta_sessao
        self._pw = None
        self._contexto = None
        self._downloads: asyncio.Queue = asyncio.Queue()

    async def __aenter__(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError as erro:
            raise ErroAutomacao(SEM_NAVEGADOR) from erro

        self._pw = await async_playwright().start()
        executavel = config.caminho_navegador
        argumentos = {
            "headless": not self.visivel,
            "accept_downloads": True,
            "locale": "pt-BR",
        }
        if executavel:
            argumentos["executable_path"] = executavel
        if config.proxy:
            argumentos["proxy"] = {"server": config.proxy, "bypass": config.proxy_excecoes}
        if config.ignorar_tls:
            argumentos["ignore_https_errors"] = True
        if self.pasta_sessao:
            # Sessão persistente: o login gov.br feito uma vez continua valendo.
            try:
                self._contexto = await self._pw.chromium.launch_persistent_context(
                    self.pasta_sessao, **argumentos
                )
            except Exception as erro:
                if amigavel := _erro_de_navegador(erro):
                    raise amigavel from erro
                raise
        else:
            lancamento = {"headless": not self.visivel}
            if executavel:
                lancamento["executable_path"] = executavel
            if config.proxy:
                lancamento["proxy"] = {"server": config.proxy, "bypass": config.proxy_excecoes}
            try:
                navegador = await self._pw.chromium.launch(**lancamento)
            except Exception as erro:
                if amigavel := _erro_de_navegador(erro):
                    raise amigavel from erro
                raise
            self._contexto = await navegador.new_context(
                accept_downloads=True,
                locale="pt-BR",
                ignore_https_errors=config.ignorar_tls,
            )
        self._contexto.set_default_timeout(30_000)
        return self

    async def __aexit__(self, *_):
        try:
            if self._contexto:
                await self._contexto.close()
        finally:
            if self._pw:
                await self._pw.stop()

    async def nova_pagina(self):
        pagina = self._contexto.pages[0] if self._contexto.pages else await self._contexto.new_page()
        pagina.on("download", lambda d: self._downloads.put_nowait(d))
        return pagina

    async def proximo_download(self, timeout: int):
        return await asyncio.wait_for(self._downloads.get(), timeout=timeout)


async def _presente(pagina, seletor: str, ms: int = 3000) -> bool:
    """O elemento está na página agora? Usado pelos passos marcados `opcional`."""
    try:
        await pagina.wait_for_selector(seletor, timeout=ms)
        return True
    except Exception:
        return False


async def _texto_da_pagina(pagina) -> str:
    try:
        return await pagina.inner_text("body")
    except Exception:
        return ""


async def _conferir_erros(pagina, passo, ctx: Contexto) -> None:
    """Aplica as regras `falhar_se_texto` da fonte ao conteúdo atual."""
    regras = passo.get("falhar_se_texto") or []
    if not regras:
        return
    texto = (await _texto_da_pagina(pagina)).lower()
    for regra in regras:
        alvo = str(regra.get("texto", "")).lower()
        if alvo and alvo in texto:
            ctx.registrar("erro_site", regra.get("mensagem", alvo))
            raise ErroAutomacao(regra.get("mensagem", alvo), repetir=bool(regra.get("repetir")))


async def _executar_passos(fonte: Fonte, ctx: Contexto, navegador: Navegador) -> Resultado:
    pagina = await navegador.nova_pagina()
    documento: bytes | None = None
    texto_pagina = ""
    aguarda_anexo = fonte.resultado == "anexo_manual"

    for passo in fonte.passos:
        acao = passo.acao
        if not passo.se_aplica(ctx.variaveis):
            ctx.registrar("passo", f"{acao} (não se aplica a este titular)")
            continue
        ctx.registrar("passo", acao)

        if acao == "abrir":
            endereco = ctx.aplicar(passo.get("url")) or fonte.url
            try:
                await pagina.goto(endereco, wait_until="domcontentloaded")
            except Exception as erro:
                if amigavel := _erro_de_navegador(erro):
                    raise amigavel from erro
                raise

        elif acao in {"clicar", "preencher", "selecionar"}:
            seletor = ctx.aplicar(passo.get("seletor"))
            # Banner de cookies, aviso de manutenção, campo que só aparece às
            # vezes: marcados `opcional`, não derrubam a emissão quando faltam.
            if passo.opcional and not await _presente(pagina, seletor, 3000):
                ctx.registrar("passo", f"{acao} {seletor} (não apareceu; seguindo)")
                continue
            if acao == "clicar":
                await pagina.click(seletor)
            elif acao == "preencher":
                await pagina.fill(seletor, ctx.aplicar(passo.get("valor")))
            else:
                await pagina.select_option(seletor, ctx.aplicar(passo.get("valor")))

        elif acao == "esperar":
            if seletor := ctx.aplicar(passo.get("seletor")):
                await pagina.wait_for_selector(seletor)
            else:
                await pagina.wait_for_timeout(int(passo.get("ms", 1000)))

        elif acao == "captcha_imagem":
            seletor = ctx.aplicar(passo.get("seletor"))
            await pagina.wait_for_selector(seletor)
            imagem = await pagina.locator(seletor).screenshot()
            resposta = await ctx.perguntar(
                tipo=TipoDesafio.CAPTCHA_IMAGEM,
                instrucao=passo.get("instrucao") or "Digite os caracteres da imagem.",
                imagem="data:image/png;base64," + base64.b64encode(imagem).decode(),
                timeout=int(passo.get("timeout", 300)),
            )
            await pagina.fill(ctx.aplicar(passo.get("campo")), resposta.strip())

        elif acao == "captcha_interativo":
            # hCaptcha e reCAPTCHA não são uma imagem que dá para recortar: são
            # um widget que reage ao mouse. A pessoa resolve na janela real, e a
            # automação segue de onde parou.
            seletor = ctx.aplicar(passo.get("seletor"))
            if seletor:
                await pagina.wait_for_selector(seletor)
            await pagina.bring_to_front()
            await ctx.perguntar(
                tipo=TipoDesafio.CAPTCHA_INTERATIVO,
                instrucao=ctx.aplicar(passo.get("instrucao")) or (
                    "Resolva o captcha na janela do navegador que está aberta e confirme aqui."
                ),
                timeout=int(passo.get("timeout", 600)),
            )
            if confirmacao := ctx.aplicar(passo.get("confirmar_seletor")):
                try:
                    await pagina.wait_for_selector(confirmacao, timeout=5_000)
                except Exception as erro:
                    raise ErroAutomacao(
                        "O site não registrou o captcha como resolvido. Tente novamente."
                    ) from erro

        elif acao == "login_gov_br":
            if sinal := ctx.aplicar(passo.get("sinal_logado")):
                # já autenticado nesta sessão: não incomoda o usuário de novo
                try:
                    await pagina.wait_for_selector(sinal, timeout=4_000)
                    ctx.registrar("sessao", "Sessão gov.br já ativa; login dispensado.")
                    continue
                except Exception:
                    pass
            await pagina.bring_to_front()
            await ctx.perguntar(
                tipo=TipoDesafio.LOGIN_GOV_BR,
                instrucao=ctx.aplicar(passo.get("instrucao")) or (
                    "Faça o login no gov.br na janela do navegador e confirme aqui. "
                    "O login vale para as próximas emissões — você não precisará repetir."
                ),
                timeout=int(passo.get("timeout", 900)),
            )

        elif acao == "abrir_no_navegador":
            # Alguns portais recusam o navegador que o sistema controla — o da
            # Receita Federal diz isso com todas as letras. Nesses casos abrimos
            # o navegador do próprio usuário, onde a sessão dele já existe, e o
            # sistema segue cuidando do arquivo e da validade.
            endereco = ctx.aplicar(passo.get("url")) or fonte.url
            ctx.registrar("navegador_do_usuario", endereco)
            try:
                webbrowser.open(endereco)
            except Exception as erro:  # pragma: no cover - depende do sistema
                ctx.registrar("aviso", f"Não consegui abrir o navegador: {erro}")

        elif acao == "acao_manual":
            aguarda_anexo = True
            await ctx.perguntar(
                tipo=TipoDesafio.ACAO_MANUAL,
                instrucao=ctx.aplicar(passo.get("instrucao")),
                timeout=int(passo.get("timeout", 900)),
            )

        elif acao == "exigir_texto":
            texto = (await _texto_da_pagina(pagina)).lower()
            alternativas = [str(a).lower() for a in (passo.get("alternativas") or [])]
            if alternativas and not any(a in texto for a in alternativas):
                raise ErroAutomacao(passo.get("mensagem") or "O site não apresentou o documento esperado.")

        elif acao == "aguardar_download":
            timeout = int(passo.get("timeout", 90))
            espera = asyncio.create_task(navegador.proximo_download(timeout))
            for _ in range(timeout):
                if espera.done():
                    break
                await _conferir_erros(pagina, passo, ctx)
                await asyncio.sleep(1)
            try:
                download = await espera
            except asyncio.TimeoutError as erro:
                await _conferir_erros(pagina, passo, ctx)
                raise ErroAutomacao("O site não entregou o arquivo no tempo esperado.") from erro
            caminho = await download.path()
            documento = caminho.read_bytes()

        elif acao == "salvar_pagina_pdf":
            texto_pagina = await _texto_da_pagina(pagina)
            documento = await pagina.pdf(format="A4", print_background=True)

        else:
            raise ErroAutomacao(f"Passo desconhecido na fonte: {acao}")

    if not texto_pagina:
        texto_pagina = await _texto_da_pagina(pagina)

    if aguarda_anexo and documento is None:
        return Resultado(
            sucesso=True,
            aguarda_anexo=True,
            mensagem="Conclua no navegador e anexe o PDF para arquivar.",
        )

    dados = analisar(documento, texto_pagina)
    return Resultado(
        sucesso=documento is not None,
        documento=documento,
        numero=dados["numero"],
        codigo_verificacao=dados["codigo_verificacao"],
        emitida_em=dados["emitida_em"] or date.today(),
        valida_ate=dados["valida_ate"],
        situacao=dados["situacao"] or SituacaoCertidao.NAO_IDENTIFICADA,
        texto_extraido=dados["texto"],
        mensagem="Documento obtido." if documento else "Nada foi obtido.",
    )


async def _sem_navegador(fonte: Fonte, ctx: Contexto) -> Resultado:
    """Fontes que só conduzem a pessoa não precisam abrir navegador nenhum."""
    for passo in fonte.passos:
        if not passo.se_aplica(ctx.variaveis):
            continue
        ctx.registrar("passo", passo.acao)
        if passo.acao == "abrir_no_navegador":
            endereco = ctx.aplicar(passo.get("url")) or fonte.url
            ctx.registrar("navegador_do_usuario", endereco)
            try:
                webbrowser.open(endereco)
            except Exception as erro:  # pragma: no cover - depende do sistema
                ctx.registrar("aviso", f"Não consegui abrir o navegador: {erro}")
        elif passo.acao == "acao_manual":
            await ctx.perguntar(
                tipo=TipoDesafio.ACAO_MANUAL,
                instrucao=ctx.aplicar(passo.get("instrucao")),
                timeout=int(passo.get("timeout", 900)),
            )
    return Resultado(
        sucesso=True, aguarda_anexo=True,
        mensagem="Conclua no navegador e anexe o PDF para arquivar.",
    )


async def executar(fonte: Fonte, ctx: Contexto) -> Resultado:
    """Uma tentativa completa da fonte, em um navegador limpo."""
    if not fonte.exige_navegador:
        return await _sem_navegador(fonte, ctx)
    async with Navegador(visivel=ctx.visivel, pasta_sessao=ctx.pasta_sessao) as navegador:
        try:
            return await _executar_passos(fonte, ctx, navegador)
        except ErroAutomacao:
            raise
        except Exception as erro:
            # Site mudou, campo sumiu, página demorou: em vez de falhar seco, a
            # fonte pode entregar o trabalho já adiantado para a pessoa
            # concluir na janela que ficou aberta na página certa.
            if fonte.ao_falhar != "pedir_anexo":
                raise
            ctx.registrar("degradou", f"A automação parou em um passo: {type(erro).__name__}")
            await ctx.perguntar(
                tipo=TipoDesafio.ACAO_MANUAL,
                instrucao=(
                    "A automação não reconheceu esta página — o site do órgão deve ter mudado. "
                    "O navegador está aberto no lugar certo: conclua a emissão por lá, salve o "
                    "PDF e anexe aqui. O controle de validade continua igual."
                ),
                timeout=900,
            )
            return Resultado(
                sucesso=True, aguarda_anexo=True,
                mensagem="A automação parou no meio; anexe o PDF emitido no site.",
            )
