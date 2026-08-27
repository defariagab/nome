from datetime import date

import pytest
from sqlalchemy import select

from certidoes import nomeacao, servicos
from certidoes.modelos import TipoCertidao


def exemplo_campos(**extras):
    base = dict(
        sigla="CNDT", codigo="cndt", certidao="Certidão Negativa de Débitos Trabalhistas",
        orgao="Tribunal Superior do Trabalho", nome="Construtora Horizonte Ltda",
        documento="11222333000181", documento_formatado="11.222.333/0001-81",
        emitida_em=date(2026, 8, 27), valida_ate=date(2027, 2, 22), numero="12345678/2026",
    )
    base.update(extras)
    return nomeacao.campos(**base)


def test_padrao_do_sistema_se_explica_sozinho():
    nome = nomeacao.aplicar(nomeacao.PADRAO, exemplo_campos())
    assert nome == "CNDT_Construtora-Horizonte-Ltda_11222333000181_valida-ate-2027-02-22.pdf"


def test_nome_seguro_em_qualquer_sistema_operacional():
    nome = nomeacao.aplicar("{sigla}_{nome}_{validade}", exemplo_campos(
        nome='Advocacia "Alfa/Beta": Ltda | ME'
    ))
    assert not set(nome) & set('<>:"/\\|?*')
    assert nome.startswith("CNDT_Advocacia-Alfa")


def test_acentos_viram_texto_simples():
    nome = nomeacao.aplicar("{nome}_{validade}", exemplo_campos(nome="Construção Ipê São João"))
    assert nome == "Construcao-Ipe-Sao-Joao_2027-02-22.pdf"


def test_campo_inexistente_nao_vaza_para_o_nome():
    nome = nomeacao.aplicar("{sigla}_{inventado}_{documento}_{validade}", exemplo_campos())
    assert "{" not in nome and "inventado" not in nome


def test_nome_longo_e_cortado():
    nome = nomeacao.aplicar("{certidao}_{orgao}_{nome}_{documento}_{validade}", exemplo_campos(
        nome="Companhia Brasileira de Empreendimentos e Participações Societárias Reunidas"
    ))
    assert len(nome) <= nomeacao.LIMITE_NOME + len(".pdf")


@pytest.mark.parametrize("padrao,erro", [
    ("", "Informe um modelo"),
    ("certidao", "ao menos um campo"),
    ("{banana}", "não existe"),
    ("{sigla}_{validade}", "{nome} ou {documento}"),
    ("{sigla}_{documento}", "{validade} ou {emissao}"),
])
def test_modelos_recusados_com_motivo(padrao, erro):
    with pytest.raises(ValueError, match=erro):
        nomeacao.validar(padrao)


def test_modelo_valido_e_aceito():
    assert nomeacao.validar(" {documento}_{sigla}_{validade} ") == "{documento}_{sigla}_{validade}"


def test_arquivamento_usa_o_padrao_do_escritorio(s, titular_exemplo):
    servicos.definir_preferencia(s, "padrao_nome_arquivo", "{documento}_{sigla}_{validade}")
    cndt = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == "cndt"))
    solicitacao = servicos.solicitar(s, titular_exemplo.id, cndt.id)
    certidao = servicos.guardar_resultado(
        s, solicitacao, documento=b"%PDF-1.4 x",
        emitida_em=date(2026, 8, 27), valida_ate=date(2027, 2, 22),
    )
    assert certidao.arquivo.endswith("11222333000181_CNDT_2027-02-22.pdf")
    assert certidao.arquivo.startswith("11222333000181/2026/")


def test_certidoes_diferentes_nao_se_sobrescrevem(s, titular_exemplo):
    """Mesmo nome, conteúdo diferente: a segunda não pode apagar a primeira."""
    servicos.definir_preferencia(s, "padrao_nome_arquivo", "{documento}_{validade}")
    cndt = s.scalar(select(TipoCertidao).where(TipoCertidao.codigo == "cndt"))
    caminhos = []
    for conteudo in (b"%PDF-1.4 primeira", b"%PDF-1.4 segunda"):
        solicitacao = servicos.solicitar(s, titular_exemplo.id, cndt.id)
        certidao = servicos.guardar_resultado(
            s, solicitacao, documento=conteudo,
            emitida_em=date(2026, 8, 27), valida_ate=date(2027, 2, 22),
        )
        caminhos.append(certidao.arquivo)
        solicitacao.estado = solicitacao.estado  # mantém a fila coerente
        s.flush()
    from certidoes import arquivos

    assert caminhos[0] != caminhos[1]
    assert arquivos.ler(caminhos[0]) == b"%PDF-1.4 primeira"
    assert arquivos.ler(caminhos[1]) == b"%PDF-1.4 segunda"
