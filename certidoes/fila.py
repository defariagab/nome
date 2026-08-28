"""Fila de execução das solicitações.

Um único laço assíncrono cuida de tudo: pega as solicitações prontas,
executa a fonte e vai anotando o andamento no banco, para que a tela
possa mostrar o que está acontecendo.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from . import servicos
from .automacao import desafios
from .automacao.motor import executar
from .automacao.fontes import carregar_fonte
from .automacao.tipos import Contexto, ErroAutomacao, Passo, Fonte
from .banco import sessao
from .config import config
from .modelos import EstadoSolicitacao, Solicitacao, TipoCertidao, Titular, agora

log = logging.getLogger("certidoes.fila")

INTERVALO = 2.0


def _fonte_para(tipo: TipoCertidao) -> Fonte:
    """Usa a fonte do tipo; sem fonte, conduz o usuário até o site."""
    if tipo.fonte and (fonte := carregar_fonte(tipo.fonte)):
        return fonte
    passos = []
    if tipo.url:
        passos.append(Passo("abrir", {"url": tipo.url}))
    passos.append(Passo("acao_manual", {
        "instrucao": (
            f"Emita a {tipo.nome} no site do órgão ({tipo.orgao}) e salve o PDF. "
            "Depois anexe o arquivo aqui para o sistema arquivar e controlar o vencimento."
        ),
    }))
    return Fonte(
        codigo=tipo.codigo, nome=tipo.nome, url=tipo.url or "",
        passos=passos, resultado="anexo_manual",
    )


def _mudar_estado(solicitacao_id: int, estado: EstadoSolicitacao, mensagem: str | None = None) -> None:
    with sessao() as s:
        solicitacao = s.get(Solicitacao, solicitacao_id)
        if solicitacao is None:
            return
        solicitacao.estado = estado
        if mensagem:
            solicitacao.mensagem = mensagem
        if estado is EstadoSolicitacao.EXECUTANDO and solicitacao.iniciada_em is None:
            solicitacao.iniciada_em = agora()
        if estado.encerrada:
            solicitacao.concluida_em = agora()


def _anotar(solicitacao_id: int, tipo: str, mensagem: str) -> None:
    with sessao() as s:
        if solicitacao := s.get(Solicitacao, solicitacao_id):
            servicos.anotar(s, solicitacao, tipo, mensagem)


class Fila:
    """Executa as solicitações, várias ao mesmo tempo quando isso ajuda.

    Emissões com captcha de letras rodam em paralelo de propósito: assim as
    imagens chegam à sala de captchas em sequência e a pessoa responde uma
    atrás da outra, sem esperar o carregamento de cada site. Já o que exige
    janela do navegador (widget interativo, login gov.br, ação manual) roda
    sozinho — não dá para pedir que alguém opere quatro janelas de uma vez.
    """

    def __init__(self, motor: str | None = None, limite: int | None = None):
        self.motor = motor
        self.limite = limite or config.paralelismo
        self._exclusivas: set[int] = set()
        self._tarefas: dict[int, asyncio.Task] = {}
        self._laco: asyncio.Task | None = None
        self._parar = asyncio.Event()

    # ------------------------------------------------------------------ ciclo
    def iniciar(self) -> None:
        if self._laco is None:
            self._parar.clear()
            self._laco = asyncio.create_task(self._rodar(), name="fila-certidoes")

    async def parar(self) -> None:
        self._parar.set()
        for tarefa in list(self._tarefas.values()):
            tarefa.cancel()
        if self._laco:
            self._laco.cancel()
            self._laco = None

    async def _rodar(self) -> None:
        while not self._parar.is_set():
            try:
                self._recolher()
                if len(self._tarefas) < self.limite:
                    for solicitacao_id in self._proximas(self.limite - len(self._tarefas)):
                        self._tarefas[solicitacao_id] = asyncio.create_task(
                            self._processar(solicitacao_id), name=f"solicitacao-{solicitacao_id}"
                        )
            except Exception:  # pragma: no cover - o laço nunca pode morrer
                log.exception("Falha no laço da fila")
            await asyncio.sleep(INTERVALO)

    def _recolher(self) -> None:
        for solicitacao_id, tarefa in list(self._tarefas.items()):
            if tarefa.done():
                self._tarefas.pop(solicitacao_id, None)
                self._exclusivas.discard(solicitacao_id)
                if (erro := tarefa.exception()) and not isinstance(erro, asyncio.CancelledError):
                    log.exception("Solicitação %s terminou com erro", solicitacao_id, exc_info=erro)

    def _ocupando_a_janela(self) -> bool:
        """Há emissão dirigindo o navegador agora?

        Enquanto ela apenas espera uma resposta da pessoa, as emissões de
        captcha de letras podem seguir: elas não disputam a janela, e travar a
        fila por causa de um pedido adiado deixaria tudo parado.
        """
        if not self._exclusivas:
            return False
        with sessao() as s:
            return any(
                (solicitacao := s.get(Solicitacao, id_)) is not None
                and solicitacao.estado is EstadoSolicitacao.EXECUTANDO
                for id_ in self._exclusivas
            )

    def _proximas(self, quantidade: int) -> list[int]:
        """Escolhe o que pode começar agora, respeitando quem precisa da janela."""
        if self._ocupando_a_janela():
            return []
        escolhidas: list[int] = []
        with sessao() as s:
            for solicitacao in s.scalars(
                select(Solicitacao)
                .where(
                    Solicitacao.estado == EstadoSolicitacao.NA_FILA,
                    Solicitacao.agendada_para <= agora(),
                )
                .order_by(Solicitacao.agendada_para, Solicitacao.id)
                .limit(quantidade * 4)
            ):
                if len(escolhidas) >= quantidade:
                    break
                if solicitacao.id in self._tarefas:
                    continue
                fonte = _fonte_para(s.get(TipoCertidao, solicitacao.tipo_certidao_id))
                if fonte.paralelizavel:
                    escolhidas.append(solicitacao.id)
                    continue
                # Exclusiva: começa sozinha, e só com a fila vazia.
                if not escolhidas and not self._tarefas and not self._exclusivas:
                    self._exclusivas.add(solicitacao.id)
                    escolhidas.append(solicitacao.id)
                    break
                # Não pode começar agora: em vez de segurar a fila, deixa passar
                # o que roda sem ajuda. Primeiro o automático, depois o que
                # precisa de gente.
                continue
        return escolhidas

    # -------------------------------------------------------------- execução
    async def _processar(self, solicitacao_id: int) -> None:
        with sessao() as s:
            solicitacao = s.get(Solicitacao, solicitacao_id)
            if solicitacao is None or solicitacao.estado is not EstadoSolicitacao.NA_FILA:
                return
            titular = s.get(Titular, solicitacao.titular_id)
            tipo = s.get(TipoCertidao, solicitacao.tipo_certidao_id)
            solicitacao.estado = EstadoSolicitacao.EXECUTANDO
            solicitacao.iniciada_em = agora()
            solicitacao.tentativas += 1
            variaveis = servicos.variaveis_do_contexto(
                titular, tipo, servicos.preferencia(s, "email_escritorio")
            )
            segredos = servicos.credenciais_de_api(s)
            nome_tipo, tipo_id = tipo.nome, tipo.id

        _anotar(solicitacao_id, "inicio", f"Iniciando {nome_tipo}.")

        async def perguntar(*, tipo, instrucao, imagem=None, timeout=300):
            _mudar_estado(solicitacao_id, EstadoSolicitacao.AGUARDANDO_HUMANO, "Aguardando você.")
            try:
                resposta = await desafios.perguntar(
                    solicitacao_id, tipo=tipo, instrucao=instrucao, imagem=imagem, timeout=timeout
                )
            finally:
                _mudar_estado(solicitacao_id, EstadoSolicitacao.EXECUTANDO)
            return resposta

        with sessao() as s:
            fonte = _fonte_para(s.get(TipoCertidao, tipo_id))

        contexto = Contexto(
            solicitacao_id=solicitacao_id,
            variaveis=variaveis,
            perguntar=perguntar,
            registrar=lambda t, m: _anotar(solicitacao_id, t, m),
            # O perfil guarda cookies e login: quem entra no gov.br uma vez
            # segue emitindo sem repetir a autenticação.
            pasta_sessao=str(config.pasta_sessoes / fonte.perfil) if fonte.perfil else None,
            visivel=config.navegador_visivel,
            segredos=segredos,
        )

        try:
            resultado = await executar(fonte, contexto, motor=self.motor)
        except desafios.DesafioExpirado as erro:
            _anotar(solicitacao_id, "cancelado", str(erro))
            _mudar_estado(solicitacao_id, EstadoSolicitacao.FALHOU, str(erro))
            return
        except ErroAutomacao as erro:
            _anotar(solicitacao_id, "falha", str(erro))
            _mudar_estado(solicitacao_id, EstadoSolicitacao.FALHOU, str(erro))
            return
        except asyncio.CancelledError:
            raise
        except Exception as erro:  # falha inesperada: guarda o diagnóstico técnico
            log.exception("Erro inesperado na solicitação %s", solicitacao_id)
            with sessao() as s:
                if solicitacao := s.get(Solicitacao, solicitacao_id):
                    solicitacao.diagnostico = f"{type(erro).__name__}: {erro}"
            _mudar_estado(
                solicitacao_id, EstadoSolicitacao.FALHOU,
                "A automação não conseguiu concluir. O site pode ter mudado — veja o detalhe técnico.",
            )
            return
        finally:
            desafios.cancelar_abertos(solicitacao_id)

        if resultado.aguarda_anexo or resultado.documento is None:
            _mudar_estado(
                solicitacao_id, EstadoSolicitacao.AGUARDANDO_ANEXO,
                resultado.mensagem or "Conclua no site do órgão e anexe o PDF aqui.",
            )
            return

        with sessao() as s:
            solicitacao = s.get(Solicitacao, solicitacao_id)
            certidao = servicos.guardar_resultado(
                s, solicitacao,
                documento=resultado.documento,
                emitida_em=resultado.emitida_em,
                valida_ate=resultado.valida_ate,
                numero=resultado.numero,
                codigo_verificacao=resultado.codigo_verificacao,
                situacao=resultado.situacao,
                extensao=resultado.extensao,
                custo=resultado.custo,
                origem="api" if resultado.custo else "automacao",
            )
            solicitacao.estado = EstadoSolicitacao.CONCLUIDA
            solicitacao.concluida_em = agora()
            nome_do_arquivo = (certidao.arquivo or "").rpartition("/")[2]
            solicitacao.mensagem = (
                f"Certidão arquivada como {nome_do_arquivo}, "
                f"válida até {certidao.valida_ate.strftime('%d/%m/%Y')}."
            )
            servicos.anotar(s, solicitacao, "concluido", solicitacao.mensagem)


fila = Fila()
