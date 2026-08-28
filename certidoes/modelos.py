"""Modelo de dados do sistema."""

from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class TipoPessoa(str, enum.Enum):
    PF = "PF"
    PJ = "PJ"


class Esfera(str, enum.Enum):
    FEDERAL = "federal"
    ESTADUAL = "estadual"
    MUNICIPAL = "municipal"


class Captcha(str, enum.Enum):
    NENHUM = "nenhum"
    #: letras numa imagem: o sistema recorta e mostra na sala de captchas
    IMAGEM = "imagem"
    #: widget interativo: resolvido na própria janela do navegador
    RECAPTCHA = "recaptcha"
    HCAPTCHA = "hcaptcha"
    DESCONHECIDO = "desconhecido"


class ModoObtencao(str, enum.Enum):
    #: o sistema emite sozinho, do início ao fim
    AUTOMATICO = "automatico"
    #: o sistema conduz, mas para e pede ajuda (captcha, login gov.br)
    ASSISTIDO = "assistido"
    #: sem automação: o sistema abre o site e o usuário anexa o PDF
    MANUAL = "manual"


class EstadoSolicitacao(str, enum.Enum):
    NA_FILA = "na_fila"
    EXECUTANDO = "executando"
    AGUARDANDO_HUMANO = "aguardando_humano"
    AGUARDANDO_ANEXO = "aguardando_anexo"
    CONCLUIDA = "concluida"
    FALHOU = "falhou"
    CANCELADA = "cancelada"

    @property
    def encerrada(self) -> bool:
        return self in {EstadoSolicitacao.CONCLUIDA, EstadoSolicitacao.FALHOU, EstadoSolicitacao.CANCELADA}


class SituacaoCertidao(str, enum.Enum):
    NEGATIVA = "negativa"
    POSITIVA_COM_EFEITO_NEGATIVO = "positiva_com_efeito_negativo"
    POSITIVA = "positiva"
    NAO_IDENTIFICADA = "nao_identificada"

    @property
    def regular(self) -> bool:
        """Situações que comprovam regularidade perante o órgão."""
        return self in {SituacaoCertidao.NEGATIVA, SituacaoCertidao.POSITIVA_COM_EFEITO_NEGATIVO}


class TipoDesafio(str, enum.Enum):
    CAPTCHA_IMAGEM = "captcha_imagem"
    #: hCaptcha/reCAPTCHA: resolvido na própria janela do navegador
    CAPTCHA_INTERATIVO = "captcha_interativo"
    LOGIN_GOV_BR = "login_gov_br"
    ACAO_MANUAL = "acao_manual"


class EstadoDesafio(str, enum.Enum):
    ABERTO = "aberto"
    RESPONDIDO = "respondido"
    EXPIRADO = "expirado"
    CANCELADO = "cancelado"


class Organizacao(Base):
    """Escritório/tenant. Hoje sempre um só; existe para permitir multiusuário depois."""

    __tablename__ = "organizacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), default="Meu escritório")
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    titulares: Mapped[list["Titular"]] = relationship(back_populates="organizacao")


class Titular(Base):
    """Pessoa física ou jurídica para quem as certidões são emitidas."""

    __tablename__ = "titular"
    __table_args__ = (UniqueConstraint("organizacao_id", "documento", name="uq_titular_documento"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organizacao_id: Mapped[int] = mapped_column(ForeignKey("organizacao.id"), default=1)
    tipo: Mapped[TipoPessoa] = mapped_column(Enum(TipoPessoa), default=TipoPessoa.PJ)
    nome: Mapped[str] = mapped_column(String(250))
    documento: Mapped[str] = mapped_column(String(14), index=True)  # só dígitos
    inscricao_estadual: Mapped[str | None] = mapped_column(String(30))
    uf: Mapped[str | None] = mapped_column(String(2))
    municipio: Mapped[str | None] = mapped_column(String(120))
    codigo_ibge: Mapped[str | None] = mapped_column(String(7))
    email: Mapped[str | None] = mapped_column(String(200))
    observacoes: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    organizacao: Mapped[Organizacao] = relationship(back_populates="titulares")
    monitoramentos: Mapped[list["Monitoramento"]] = relationship(
        back_populates="titular", cascade="all, delete-orphan"
    )
    certidoes: Mapped[list["Certidao"]] = relationship(back_populates="titular", cascade="all, delete-orphan")


class TipoCertidao(Base):
    """Catálogo: cada espécie de certidão emitida por um órgão."""

    __tablename__ = "tipo_certidao"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(200))
    sigla: Mapped[str | None] = mapped_column(String(30))
    orgao: Mapped[str] = mapped_column(String(200))
    esfera: Mapped[Esfera] = mapped_column(Enum(Esfera))
    uf: Mapped[str | None] = mapped_column(String(2))
    municipio: Mapped[str | None] = mapped_column(String(120))
    aplica_pf: Mapped[bool] = mapped_column(Boolean, default=True)
    aplica_pj: Mapped[bool] = mapped_column(Boolean, default=True)
    validade_dias: Mapped[int] = mapped_column(Integer, default=90)
    requer_gov_br: Mapped[bool] = mapped_column(Boolean, default=False)
    requer_certificado: Mapped[bool] = mapped_column(Boolean, default=False)
    captcha: Mapped[Captcha] = mapped_column(Enum(Captcha), default=Captcha.DESCONHECIDO)
    modo: Mapped[ModoObtencao] = mapped_column(Enum(ModoObtencao), default=ModoObtencao.MANUAL)
    fonte: Mapped[str | None] = mapped_column(String(60))
    url: Mapped[str | None] = mapped_column(String(500))
    #: quando os seletores da fonte foram conferidos contra o site real
    verificado_em: Mapped[date | None] = mapped_column(Date)
    observacoes: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class Monitoramento(Base):
    """Vínculo "este titular precisa manter esta certidão vigente"."""

    __tablename__ = "monitoramento"
    __table_args__ = (UniqueConstraint("titular_id", "tipo_certidao_id", name="uq_monitoramento"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    titular_id: Mapped[int] = mapped_column(ForeignKey("titular.id", ondelete="CASCADE"))
    tipo_certidao_id: Mapped[int] = mapped_column(ForeignKey("tipo_certidao.id"))
    renovar_automaticamente: Mapped[bool] = mapped_column(Boolean, default=True)
    dias_antecedencia: Mapped[int] = mapped_column(Integer, default=15)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    titular: Mapped[Titular] = relationship(back_populates="monitoramentos")
    tipo: Mapped[TipoCertidao] = relationship()


class Certidao(Base):
    """Documento emitido e arquivado."""

    __tablename__ = "certidao"

    id: Mapped[int] = mapped_column(primary_key=True)
    titular_id: Mapped[int] = mapped_column(ForeignKey("titular.id", ondelete="CASCADE"))
    tipo_certidao_id: Mapped[int] = mapped_column(ForeignKey("tipo_certidao.id"))
    numero: Mapped[str | None] = mapped_column(String(120))
    codigo_verificacao: Mapped[str | None] = mapped_column(String(120))
    emitida_em: Mapped[date] = mapped_column(Date)
    valida_ate: Mapped[date] = mapped_column(Date, index=True)
    situacao: Mapped[SituacaoCertidao] = mapped_column(
        Enum(SituacaoCertidao), default=SituacaoCertidao.NAO_IDENTIFICADA
    )
    arquivo: Mapped[str | None] = mapped_column(String(400))
    arquivo_hash: Mapped[str | None] = mapped_column(String(64))
    origem: Mapped[str] = mapped_column(String(20), default="automacao")  # automacao | upload | api
    #: quanto a emissão custou, quando veio de uma API paga (em reais)
    custo: Mapped[float] = mapped_column(Float, default=0.0)
    solicitacao_id: Mapped[int | None] = mapped_column(ForeignKey("solicitacao.id"))
    substituida: Mapped[bool] = mapped_column(Boolean, default=False)
    observacoes: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    titular: Mapped[Titular] = relationship(back_populates="certidoes")
    tipo: Mapped[TipoCertidao] = relationship()


class Solicitacao(Base):
    """Uma tentativa de obter uma certidão (item da fila de automação)."""

    __tablename__ = "solicitacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    titular_id: Mapped[int] = mapped_column(ForeignKey("titular.id", ondelete="CASCADE"))
    tipo_certidao_id: Mapped[int] = mapped_column(ForeignKey("tipo_certidao.id"))
    estado: Mapped[EstadoSolicitacao] = mapped_column(
        Enum(EstadoSolicitacao), default=EstadoSolicitacao.NA_FILA, index=True
    )
    origem: Mapped[str] = mapped_column(String(20), default="manual")  # manual | renovacao
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    agendada_para: Mapped[datetime] = mapped_column(DateTime, default=agora, index=True)
    iniciada_em: Mapped[datetime | None] = mapped_column(DateTime)
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime)
    mensagem: Mapped[str | None] = mapped_column(Text)
    diagnostico: Mapped[str | None] = mapped_column(Text)
    registro: Mapped[list | None] = mapped_column(JSON, default=list)
    certidao_id: Mapped[int | None] = mapped_column(ForeignKey("certidao.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)

    titular: Mapped[Titular] = relationship()
    tipo: Mapped[TipoCertidao] = relationship()
    desafios: Mapped[list["Desafio"]] = relationship(
        back_populates="solicitacao", cascade="all, delete-orphan"
    )


class Desafio(Base):
    """Pedido de ajuda humana durante a automação (captcha, login gov.br...)."""

    __tablename__ = "desafio"

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitacao_id: Mapped[int] = mapped_column(ForeignKey("solicitacao.id", ondelete="CASCADE"))
    tipo: Mapped[TipoDesafio] = mapped_column(Enum(TipoDesafio))
    estado: Mapped[EstadoDesafio] = mapped_column(Enum(EstadoDesafio), default=EstadoDesafio.ABERTO, index=True)
    instrucao: Mapped[str] = mapped_column(Text)
    imagem: Mapped[str | None] = mapped_column(Text)  # data URI (PNG em base64)
    resposta: Mapped[str | None] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)
    expira_em: Mapped[datetime | None] = mapped_column(DateTime)
    respondido_em: Mapped[datetime | None] = mapped_column(DateTime)

    solicitacao: Mapped[Solicitacao] = relationship(back_populates="desafios")


class Credencial(Base):
    """Credencial de acesso (gov.br etc). O segredo é gravado cifrado."""

    __tablename__ = "credencial"

    id: Mapped[int] = mapped_column(primary_key=True)
    organizacao_id: Mapped[int] = mapped_column(ForeignKey("organizacao.id"), default=1)
    titular_id: Mapped[int | None] = mapped_column(ForeignKey("titular.id", ondelete="CASCADE"))
    rotulo: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(30), default="gov_br")
    usuario: Mapped[str | None] = mapped_column(String(120))
    segredo: Mapped[str | None] = mapped_column(Text)  # cifrado
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora)


class Configuracao(Base):
    """Preferências do escritório, editáveis pela tela."""

    __tablename__ = "configuracao"

    chave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(Text)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=agora, onupdate=agora)


class Evento(Base):
    """Trilha de auditoria: quem/o quê aconteceu com cada registro."""

    __tablename__ = "evento"

    id: Mapped[int] = mapped_column(primary_key=True)
    entidade: Mapped[str] = mapped_column(String(40), index=True)
    entidade_id: Mapped[int | None] = mapped_column(Integer, index=True)
    tipo: Mapped[str] = mapped_column(String(60))
    mensagem: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=agora, index=True)
