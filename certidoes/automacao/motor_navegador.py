"""Execução das receitas em um navegador real (Playwright/Chromium).

Sites de órgãos públicos são, na prática, aplicações JSF cheias de AJAX,
sessão e captcha. Conduzir um navegador de verdade é mais confiável do que
tentar reproduzir as requisições — e é o que permite entregar a imagem do
captcha ao usuário e seguir de onde parou depois da resposta dele.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import date

from ..config import config
from ..modelos import SituacaoCertidao, TipoDesafio
from .extracao import analisar
from .tipos import Contexto, ErroAutomacao, Receita, Resultado

class Navegador:
    """Envolve o Playwright e mantém a sessão (cookies, login gov.br)."""

    def __init__(self, *, visivel: bool = True, pasta_sessao: str | None = None):
        self.visivel = visivel
        self.pasta_sessao = pasta_sessao
        self._pw = None
        self._contexto = None
        self._downloads: asyncio.Queue = asyncio.Queue()

    async def __aenter__(self):
        from playwright.async_api import async_playwright

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
            self._contexto = await self._pw.chromium.launch_persistent_context(
                self.pasta_sessao, **argumentos
            )
        else:
            lancamento = {"headless": not self.visivel}
            if executavel:
                lancamento["executable_path"] = executavel
            if config.proxy:
                lancamento["proxy"] = {"server": config.proxy, "bypass": config.proxy_excecoes}
            navegador = await self._pw.chromium.launch(**lancamento)
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


async def _texto_da_pagina(pagina) -> str:
    try:
        return await pagina.inner_text("body")
    except Exception:
        return ""


async def _conferir_erros(pagina, passo, ctx: Contexto) -> None:
    """Aplica as regras `falhar_se_texto` da receita ao conteúdo atual."""
    regras = passo.get("falhar_se_texto") or []
    if not regras:
        return
    texto = (await _texto_da_pagina(pagina)).lower()
    for regra in regras:
        alvo = str(regra.get("texto", "")).lower()
        if alvo and alvo in texto:
            ctx.registrar("erro_site", regra.get("mensagem", alvo))
            raise ErroAutomacao(regra.get("mensagem", alvo), repetir=bool(regra.get("repetir")))


async def _executar_passos(receita: Receita, ctx: Contexto, navegador: Navegador) -> Resultado:
    pagina = await navegador.nova_pagina()
    documento: bytes | None = None
    texto_pagina = ""
    aguarda_anexo = receita.resultado == "anexo_manual"

    for passo in receita.passos:
        acao = passo.acao
        ctx.registrar("passo", acao)

        if acao == "abrir":
            await pagina.goto(ctx.aplicar(passo.get("url")) or receita.url, wait_until="domcontentloaded")

        elif acao == "clicar":
            await pagina.click(ctx.aplicar(passo.get("seletor")))

        elif acao == "preencher":
            await pagina.fill(ctx.aplicar(passo.get("seletor")), ctx.aplicar(passo.get("valor")))

        elif acao == "selecionar":
            await pagina.select_option(
                ctx.aplicar(passo.get("seletor")), ctx.aplicar(passo.get("valor"))
            )

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
            raise ErroAutomacao(f"Passo desconhecido na receita: {acao}")

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


async def executar(receita: Receita, ctx: Contexto) -> Resultado:
    """Uma tentativa completa da receita, em um navegador limpo."""
    async with Navegador(visivel=ctx.visivel, pasta_sessao=ctx.pasta_sessao) as navegador:
        try:
            return await _executar_passos(receita, ctx, navegador)
        except ErroAutomacao:
            raise
        except Exception as erro:
            # Site mudou, campo sumiu, página demorou: em vez de falhar seco, a
            # receita pode entregar o trabalho já adiantado para a pessoa
            # concluir na janela que ficou aberta na página certa.
            if receita.ao_falhar != "pedir_anexo":
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
