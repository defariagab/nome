"""Quem pode rodar junto e quem precisa da janela só para si.

Emissões com captcha de letras rodam em paralelo de propósito: é o que faz
40 certidões virarem alguns minutos de digitação em vez de 40 esperas.
"""

from sqlalchemy import select

from certidoes import servicos
from certidoes.automacao.fontes import carregar_fonte
from certidoes.automacao.tipos import Passo, Fonte
from certidoes.banco import sessao
from certidoes.fila import Fila
from certidoes.modelos import TipoCertidao


def fonte(*acoes, **extras):
    return Fonte(
        codigo="t", nome="t", url="", passos=[Passo(a, {}) for a in acoes], **extras
    )


def test_captcha_de_letras_roda_em_paralelo():
    assert fonte("abrir", "captcha_imagem", "clicar").paralelizavel
    assert carregar_fonte("cndt").paralelizavel
    assert carregar_fonte("fgts_crf").paralelizavel


def test_o_que_exige_a_janela_roda_sozinho():
    assert not fonte("abrir", "captcha_interativo").paralelizavel
    assert not fonte("abrir", "login_gov_br").paralelizavel
    assert not fonte("abrir", "acao_manual").paralelizavel
    assert not carregar_fonte("rfb_pgfn_conjunta").paralelizavel


def test_sessao_reaproveitada_impede_paralelismo():
    """Um perfil de navegador não pode ser aberto por duas janelas ao mesmo tempo."""
    assert not fonte("abrir", "preencher", perfil="govbr").paralelizavel


def _enfileirar(codigo: str, quantos: int) -> None:
    with sessao() as s:
        tipo = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == codigo))
        for i in range(quantos):
            titular = servicos.salvar_titular(s, {
                "nome": f"Empresa {i}",
                "documento": ["11222333000181", "34028316000103", "52998224725",
                              "11444777000161", "13347016000117"][i],
            })
            s.flush()
            servicos.solicitar(s, titular.id, tipo.id)


def test_varias_emissoes_de_captcha_comecam_juntas():
    _enfileirar("cndt", 4)
    fila = Fila(motor="simulador", limite=4)
    assert len(fila._proximas(4)) == 4


def test_emissao_com_janela_segura_a_vez():
    _enfileirar("rfb_pgfn_conjunta", 3)  # captcha interativo: uma de cada vez
    fila = Fila(motor="simulador", limite=4)
    primeira = fila._proximas(4)
    assert len(primeira) == 1
    assert fila._exclusivas == set(primeira)
    assert fila._proximas(4) == []  # nada entra enquanto a janela está com o usuário


def test_limite_de_paralelismo_e_respeitado():
    _enfileirar("cndt", 5)
    fila = Fila(motor="simulador", limite=2)
    assert len(fila._proximas(2)) == 2


def test_pedido_adiado_nao_trava_a_fila():
    """Uma emissão esperando o usuário não pode parar as demais."""
    from certidoes.modelos import EstadoSolicitacao, Solicitacao

    _enfileirar("rfb_pgfn_conjunta", 3)
    fila = Fila(motor="simulador", limite=4)
    exclusiva = fila._proximas(4)[0]  # a primeira que precisa da janela vai sozinha

    with sessao() as s:  # e então ela para, esperando a pessoa
        s.get(Solicitacao, exclusiva).estado = EstadoSolicitacao.AGUARDANDO_HUMANO
    fila._tarefas.clear()

    _enfileirar_extra("cndt", 2)
    seguintes = fila._proximas(4)
    assert len(seguintes) == 2  # as de captcha de letras seguem
    assert exclusiva not in seguintes


def _enfileirar_extra(codigo: str, quantos: int) -> None:
    from certidoes.modelos import Titular

    with sessao() as s:
        tipo = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == codigo))
        for titular in list(s.scalars(select(Titular)))[:quantos]:
            servicos.solicitar(s, titular.id, tipo.id)


def test_falta_de_navegador_vira_instrucao_e_nao_culpa_do_site():
    """A mensagem precisa dizer o que fazer, não mandar procurar o que não quebrou."""
    from certidoes.automacao.motor_navegador import SEM_NAVEGADOR, _erro_de_navegador

    faltando = _erro_de_navegador(Exception(
        "BrowserType.launch: Executable doesn't exist at /opt/pw/chromium/chrome\n"
        "Please run the following command to download new browsers"
    ))
    assert faltando is not None
    assert str(faltando) == SEM_NAVEGADOR
    assert "iniciar.bat" in str(faltando)

    sem_rede = _erro_de_navegador(Exception("net::ERR_INTERNET_DISCONNECTED at https://x"))
    assert "conexão com a internet" in str(sem_rede)

    fora_do_ar = _erro_de_navegador(Exception("net::ERR_CONNECTION_RESET at https://x"))
    assert "fora do ar" in str(fora_do_ar)

    # o que não é de infraestrutura continua seguindo o caminho normal
    assert _erro_de_navegador(Exception("Timeout 30000ms exceeded waiting for selector")) is None


def test_passo_opcional_nao_derruba_a_emissao():
    """Banner de cookies que às vezes aparece não pode quebrar a fonte."""
    from certidoes.automacao.tipos import Passo

    assert Passo("clicar", {"seletor": "#cookies", "opcional": True}).opcional
    assert not Passo("clicar", {"seletor": "#cookies"}).opcional
