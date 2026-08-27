"""Testes da API — o mesmo caminho que a tela usa."""

import pytest
from fastapi.testclient import TestClient

from certidoes.api.app import app


@pytest.fixture
def cliente(monkeypatch):
    # a fila e a renovação periódica são exercitadas em test_fila.py
    monkeypatch.setattr("certidoes.fila.fila.iniciar", lambda: None)

    async def _sem_agenda(*_args, **_kwargs):
        return None

    monkeypatch.setattr("certidoes.agenda.rodar_periodicamente", _sem_agenda)
    with TestClient(app) as c:
        yield c


def criar_titular(cliente, **extras):
    corpo = {"nome": "Empresa Exemplo Ltda", "documento": "11.222.333/0001-81", "uf": "SP", **extras}
    return cliente.post("/api/titulares", json=corpo)


def test_catalogo_disponivel(cliente):
    tipos = cliente.get("/api/tipos").json()
    codigos = {t["codigo"] for t in tipos}
    assert {"cndt", "fgts_crf", "rfb_pgfn_conjunta"} <= codigos
    cndt = next(t for t in tipos if t["codigo"] == "cndt")
    assert cndt["captcha"] == "imagem"
    assert cndt["validade_dias"] == 180


def test_cadastro_e_painel(cliente):
    tipos = cliente.get("/api/tipos").json()
    cndt = next(t for t in tipos if t["codigo"] == "cndt")

    resposta = criar_titular(cliente, monitoramentos=[cndt["id"]])
    assert resposta.status_code == 200
    assert resposta.json()["documento_formatado"] == "11.222.333/0001-81"

    painel = cliente.get("/api/painel").json()
    assert len(painel) == 1
    assert painel[0]["status"] == "ausente"

    resumo = cliente.get("/api/resumo").json()
    assert resumo["titulares"] == 1
    assert resumo["pendencias"] == 1


def test_documento_invalido_devolve_mensagem_util(cliente):
    resposta = cliente.post("/api/titulares", json={"nome": "X", "documento": "123"})
    assert resposta.status_code == 400
    assert "inválido" in resposta.json()["erro"]


def test_emitir_pendentes_enfileira_tudo(cliente):
    tipos = cliente.get("/api/tipos").json()
    escolhidos = [t["id"] for t in tipos if t["codigo"] in {"cndt", "fgts_crf"}]
    criar_titular(cliente, monitoramentos=escolhidos)

    resultado = cliente.post("/api/solicitacoes/pendentes").json()
    assert resultado["criadas"] == 2

    # chamar de novo não duplica o que já está na fila
    assert cliente.post("/api/solicitacoes/pendentes").json()["criadas"] == 0

    solicitacoes = cliente.get("/api/solicitacoes").json()
    assert {s["estado"] for s in solicitacoes} == {"na_fila"}


def test_anexar_pdf_arquiva_e_conclui(cliente):
    from certidoes.automacao.pdf_simples import gerar

    tipos = cliente.get("/api/tipos").json()
    cndt = next(t for t in tipos if t["codigo"] == "cndt")
    titular = criar_titular(cliente, monitoramentos=[cndt["id"]]).json()
    solicitacao = cliente.post(
        "/api/solicitacoes", json={"titular_id": titular["id"], "tipo_id": cndt["id"]}
    ).json()

    pdf = gerar(["Certidao n. 77/2026", "Validade: 15/12/2026", "CERTIDAO NEGATIVA"], "CNDT")
    resposta = cliente.post(
        f"/api/solicitacoes/{solicitacao['id']}/anexar",
        files={"arquivo": ("certidao.pdf", pdf, "application/pdf")},
    )
    assert resposta.status_code == 200
    assert resposta.json()["valida_ate"] == "2026-12-15"

    painel = cliente.get("/api/painel").json()
    assert painel[0]["status"] in {"vigente", "vence_em_breve", "vencida"}
    assert painel[0]["tem_arquivo"]

    certidao_id = painel[0]["certidao_id"]
    arquivo = cliente.get(f"/api/certidoes/{certidao_id}/arquivo")
    assert arquivo.status_code == 200
    assert arquivo.content.startswith(b"%PDF")


def test_cancelar_solicitacao(cliente):
    tipos = cliente.get("/api/tipos").json()
    cndt = next(t for t in tipos if t["codigo"] == "cndt")
    titular = criar_titular(cliente, monitoramentos=[cndt["id"]]).json()
    solicitacao = cliente.post(
        "/api/solicitacoes", json={"titular_id": titular["id"], "tipo_id": cndt["id"]}
    ).json()

    assert cliente.post(f"/api/solicitacoes/{solicitacao['id']}/cancelar").status_code == 200
    assert cliente.post(f"/api/solicitacoes/{solicitacao['id']}/cancelar").status_code == 400


def test_ajuste_de_tipo_persiste(cliente):
    tipos = cliente.get("/api/tipos").json()
    municipal = next(t for t in tipos if t["codigo"] == "municipal_tributos")
    resposta = cliente.put(
        f"/api/tipos/{municipal['id']}",
        json={"url": "https://prefeitura.exemplo.gov.br/cnd", "validade_dias": 60},
    )
    assert resposta.json()["url"] == "https://prefeitura.exemplo.gov.br/cnd"
    assert resposta.json()["validade_dias"] == 60


def test_painel_web_responde(cliente):
    assert cliente.get("/").status_code == 200
    assert cliente.get("/web/app.js").status_code == 200
    assert cliente.get("/api/saude").json()["ok"] is True


def test_preferencia_de_nome_de_arquivo(cliente):
    padrao = cliente.get("/api/preferencias").json()
    assert padrao["exemplo"].endswith(".pdf")
    assert "sigla" in padrao["campos"]

    salvo = cliente.put(
        "/api/preferencias", json={"padrao_nome_arquivo": "{documento}_{sigla}_{validade}"}
    ).json()
    assert salvo["exemplo"] == "11222333000181_CNDT_2027-02-22.pdf"
    assert cliente.get("/api/preferencias").json()["padrao_nome_arquivo"] == "{documento}_{sigla}_{validade}"


def test_modelo_de_nome_invalido_explica_o_motivo(cliente):
    resposta = cliente.put("/api/preferencias", json={"padrao_nome_arquivo": "{sigla}"})
    assert resposta.status_code == 400
    assert "{nome} ou {documento}" in resposta.json()["erro"]


def test_inspecao_exige_endereco_completo(cliente):
    resposta = cliente.post("/api/inspecionar", json={"url": "fonte.fazenda.gov.br"})
    assert resposta.status_code == 400
    assert "https://" in resposta.json()["erro"]


def test_catalogo_traz_os_portais_novos(cliente):
    tipos = {t["codigo"]: t for t in cliente.get("/api/tipos").json()}
    assert tipos["rfb_pgfn_conjunta"]["captcha"] == "hcaptcha"
    assert "servicos.receitafederal.gov.br" in tipos["rfb_pgfn_conjunta"]["url"]
    assert "certidao-unificada.cjf.jus.br" in tipos["jf_certidao_unificada"]["url"]
    assert "TRF6" in tipos["jf_certidao_unificada"]["observacoes"]


def test_dossie_reune_as_certidoes_vigentes(cliente):
    from certidoes.automacao.pdf_simples import gerar

    tipos = {t["codigo"]: t for t in cliente.get("/api/tipos").json()}
    titular = criar_titular(cliente, monitoramentos=[tipos["cndt"]["id"]]).json()

    solicitacao = cliente.post(
        "/api/solicitacoes", json={"titular_id": titular["id"], "tipo_id": tipos["cndt"]["id"]}
    ).json()
    pdf = gerar(["Certidao n. 90/2026", "Validade: 31/12/2030", "CERTIDAO NEGATIVA"], "CNDT")
    cliente.post(f"/api/solicitacoes/{solicitacao['id']}/anexar",
                 files={"arquivo": ("c.pdf", pdf, "application/pdf")})

    resposta = cliente.get(f"/api/titulares/{titular['id']}/dossie")
    assert resposta.status_code == 200
    assert resposta.content.startswith(b"%PDF")
    assert "dossie_11222333000181" in resposta.headers["content-disposition"]


def test_dossie_sem_certidao_explica_o_que_fazer(cliente):
    titular = criar_titular(cliente).json()
    resposta = cliente.get(f"/api/titulares/{titular['id']}/dossie")
    assert resposta.status_code == 400
    assert "Emita ou anexe" in resposta.json()["erro"]


def test_relatorio_de_conferencia_so_existe_depois_de_conferir(cliente):
    assert cliente.get("/api/diagnostico/relatorio").status_code == 404


def test_email_do_escritorio_recebe_as_copias(cliente):
    salvo = cliente.put("/api/preferencias", json={
        "padrao_nome_arquivo": "{sigla}_{documento}_{validade}",
        "email_escritorio": "contato@escritorio.adv.br",
    }).json()
    assert salvo["email_escritorio"] == "contato@escritorio.adv.br"
    assert cliente.get("/api/preferencias").json()["email_escritorio"] == "contato@escritorio.adv.br"


def test_email_do_escritorio_invalido_e_recusado(cliente):
    resposta = cliente.put("/api/preferencias", json={
        "padrao_nome_arquivo": "{sigla}_{documento}_{validade}",
        "email_escritorio": "isso nao e email",
    })
    assert resposta.status_code == 400
    assert "não parece válido" in resposta.json()["erro"]


def test_exclusoes_pela_api(cliente):
    from certidoes.automacao.pdf_simples import gerar

    tipos = {t["codigo"]: t for t in cliente.get("/api/tipos").json()}
    titular = criar_titular(cliente, monitoramentos=[tipos["cndt"]["id"]]).json()
    solicitacao = cliente.post(
        "/api/solicitacoes", json={"titular_id": titular["id"], "tipo_id": tipos["cndt"]["id"]}
    ).json()
    pdf = gerar(["Certidao n. 5/2026", "Validade: 31/12/2030", "CERTIDAO NEGATIVA"], "CNDT")
    cliente.post(f"/api/solicitacoes/{solicitacao['id']}/anexar",
                 files={"arquivo": ("c.pdf", pdf, "application/pdf")})

    previa = cliente.get(f"/api/titulares/{titular['id']}/o-que-sera-excluido").json()
    assert previa["certidoes"] == 1 and previa["solicitacoes"] == 1

    certidao_id = cliente.get("/api/painel").json()[0]["certidao_id"]
    assert cliente.delete(f"/api/certidoes/{certidao_id}").status_code == 200
    assert cliente.get("/api/certidoes").json() == []

    assert cliente.delete(f"/api/solicitacoes/{solicitacao['id']}").status_code == 200
    assert cliente.get("/api/solicitacoes").json() == []

    assert cliente.delete(f"/api/titulares/{titular['id']}?definitivo=true").status_code == 200
    assert cliente.get("/api/titulares").json() == []


def test_diagnostico_das_emissoes_sai_legivel(cliente):
    tipos = {t["codigo"]: t for t in cliente.get("/api/tipos").json()}
    titular = criar_titular(cliente, monitoramentos=[tipos["cndt"]["id"]]).json()
    cliente.post("/api/solicitacoes",
                 json={"titular_id": titular["id"], "tipo_id": tipos["cndt"]["id"]})

    resposta = cliente.get("/api/diagnostico/emissoes")
    assert resposta.status_code == 200
    texto = resposta.content.decode()
    assert "Diagnóstico das emissões" in texto
    assert "Certidão Negativa de Débitos Trabalhistas" in texto
    assert "estado: na_fila" in texto


def test_desativar_titular_continua_sendo_o_padrao(cliente):
    titular = criar_titular(cliente).json()
    assert cliente.delete(f"/api/titulares/{titular['id']}").status_code == 200
    assert cliente.get("/api/titulares").json() == []                      # some da lista
    assert cliente.get("/api/titulares?incluir_inativos=true").json() != []  # mas não foi apagado
