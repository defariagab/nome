"""Emissão por API contratada — o caminho oficial, sem captcha."""

import asyncio
from datetime import date

import pytest

from certidoes.automacao.motor_api import CredencialAusente, buscar, executar
from certidoes.automacao.tipos import Contexto, ErroAutomacao, Fonte
from certidoes.modelos import SituacaoCertidao
from testes.api_falsa import TOKEN, ApiFalsa


def _fonte(endereco: str, **extras) -> Fonte:
    api = {
        "endereco": endereco,
        "metodo": "GET",
        "credencial": "serpro_cnd",
        "parametros": {"ni": "{documento}"},
        "custo_por_emissao": 0.87,
        "resposta": {
            "documento": "dados.certidao",
            "numero": "dados.numeroCertidao",
            "emissao": "dados.dataEmissao",
            "validade": "dados.dataValidade",
            "situacao": "dados.tipoCertidao",
            "erro": "mensagem",
            "formato_de_data": "%d/%m/%Y",
        },
    }
    api.update(extras)
    return Fonte(codigo="cnd_api", nome="CND por API", url=endereco, passos=[], tipo="api", api=api)


def _contexto(documento="11222333000181", token=TOKEN) -> Contexto:
    async def nao_pergunta(**_kwargs):
        return ""

    return Contexto(
        solicitacao_id=0,
        variaveis={"documento": documento, "documento_formatado": documento},
        perguntar=nao_pergunta, registrar=lambda t, m: None,
        segredos={"serpro_cnd": token} if token else {},
    )


def test_emite_pela_api_com_custo_registrado():
    with ApiFalsa() as api:
        resultado = asyncio.run(executar(_fonte(api.url), _contexto(), token=TOKEN))

    assert resultado.sucesso
    assert resultado.documento.startswith(b"%PDF")
    assert resultado.numero == "API-2026/0001"
    assert resultado.emitida_em == date(2026, 8, 28)
    assert resultado.valida_ate == date(2027, 2, 24)
    assert resultado.situacao is SituacaoCertidao.NEGATIVA
    assert resultado.custo == 0.87


def test_sem_token_o_sistema_diz_onde_cadastrar():
    with ApiFalsa() as api:
        with pytest.raises(CredencialAusente, match="Credenciais de API"):
            asyncio.run(executar(_fonte(api.url), _contexto(token=None), token=None))


def test_token_recusado_e_explicado():
    with ApiFalsa() as api:
        with pytest.raises(CredencialAusente, match="recusou a credencial"):
            asyncio.run(executar(_fonte(api.url), _contexto(token="errado"), token="errado"))


def test_mensagem_de_erro_da_api_chega_ao_usuario():
    with ApiFalsa() as api:
        with pytest.raises(ErroAutomacao, match="pendencias impeditivas"):
            asyncio.run(executar(_fonte(api.url), _contexto("00000000000000"), token=TOKEN))


def test_resposta_sem_arquivo_nao_vira_certidao():
    with ApiFalsa() as api:
        with pytest.raises(ErroAutomacao, match="não trouxe o arquivo"):
            asyncio.run(executar(_fonte(api.url), _contexto("11111111111111"), token=TOKEN))


def test_limite_de_chamadas_e_dito_pelo_nome():
    with ApiFalsa() as api:
        fonte = _fonte(api.url.replace("/certidao", "/limite"))
        with pytest.raises(ErroAutomacao, match="limite de chamadas"):
            asyncio.run(executar(fonte, _contexto(), token=TOKEN))


def test_api_fora_do_ar_nao_derruba_o_sistema():
    fonte = _fonte("http://127.0.0.1:9/consulta")  # porta que não atende
    with pytest.raises(ErroAutomacao, match="Não consegui falar com a API"):
        asyncio.run(executar(fonte, _contexto(), token=TOKEN))


@pytest.mark.parametrize("caminho,esperado", [
    ("dados.certidao", "abc"),
    ("itens.0.pdf", "primeiro"),
    ("itens.5.pdf", None),
    ("nao.existe", None),
    ("", {"dados": {"certidao": "abc"}, "itens": [{"pdf": "primeiro"}]}),
])
def test_leitura_de_campos_da_resposta(caminho, esperado):
    dados = {"dados": {"certidao": "abc"}, "itens": [{"pdf": "primeiro"}]}
    assert buscar(dados, caminho) == esperado
