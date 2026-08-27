"""Descobre os campos de um site de órgão, para completar uma receita.

Sites de tribunal, SEFAZ e prefeitura são todos diferentes. Em vez de exigir
que alguém leia o HTML, esta ferramenta abre a página, lista os campos e já
sugere o seletor de cada um — é o que transforma "só um programador adiciona
um órgão novo" em "o escritório adiciona".
"""

from __future__ import annotations

from .motor_navegador import Navegador

#: roda no navegador: descreve cada controle da página de forma utilizável
_EXTRAIR = """
() => {
  const rotulo = (el) => {
    if (el.labels && el.labels.length) return el.labels[0].innerText.trim();
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    const pai = el.closest('label');
    return pai ? pai.innerText.trim() : '';
  };
  const seletor = (el) => {
    const attrs = ['formcontrolname', 'name', 'data-testid'];
    if (el.id) return `[id="${el.id}"]`;
    for (const a of attrs) {
      const v = el.getAttribute(a);
      if (v) return `${el.tagName.toLowerCase()}[${a}="${v}"]`;
    }
    if (el.tagName === 'BUTTON' && el.innerText.trim()) {
      return `button:has-text("${el.innerText.trim().slice(0, 40)}")`;
    }
    if (el.type) return `${el.tagName.toLowerCase()}[type="${el.type}"]`;
    return el.tagName.toLowerCase();
  };
  const alvos = document.querySelectorAll('input, select, textarea, button, iframe, img');
  return [...alvos].slice(0, 120).map((el) => ({
    marcador: el.tagName.toLowerCase(),
    tipo: el.type || '',
    seletor: seletor(el),
    rotulo: rotulo(el),
    texto: (el.innerText || el.value || '').trim().slice(0, 60),
    fonte: (el.getAttribute('src') || '').slice(0, 120),
    alternativo: (el.getAttribute('alt') || el.getAttribute('title') || '').slice(0, 80),
    visivel: !!(el.offsetWidth || el.offsetHeight),
  })).filter((c) => c.visivel || c.marcador === 'iframe');
}
"""


def _classificar(campo: dict) -> str:
    """Diz para que serve o campo, na linguagem da receita."""
    texto = " ".join([
        campo["rotulo"], campo["texto"], campo["seletor"],
        campo["fonte"], campo.get("alternativo", ""),
    ]).lower()
    if campo["marcador"] == "iframe" or "captcha" in texto:
        if any(marca in texto for marca in ("hcaptcha", "recaptcha", "turnstile")):
            return "captcha_interativo"
        return "captcha_imagem"
    if campo["marcador"] == "button" or campo["tipo"] in {"submit", "button"}:
        return "clicar"
    if campo["marcador"] == "select":
        return "selecionar"
    if campo["marcador"] == "img":
        return "imagem"
    if any(marca in texto for marca in ("cnpj", "cpf", "inscri", "documento", "ni")):
        return "preencher (documento)"
    return "preencher"


async def inspecionar(url: str, espera: int = 0, visivel: bool = True) -> dict:
    """Abre a página e devolve os campos encontrados.

    ``espera`` dá tempo para a pessoa navegar até a tela certa antes da
    captura — útil quando o formulário está depois de um menu ou de um login.
    """
    async with Navegador(visivel=visivel) as navegador:
        pagina = await navegador.nova_pagina()
        await pagina.goto(url, wait_until="domcontentloaded")
        try:
            await pagina.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass  # SPA que continua conversando com o servidor: seguimos assim mesmo
        if espera > 0:
            await pagina.wait_for_timeout(min(espera, 300) * 1000)
        campos = await pagina.evaluate(_EXTRAIR)
        titulo = await pagina.title()
        endereco = pagina.url

    for campo in campos:
        campo["sugestao"] = _classificar(campo)
    return {"url": endereco, "titulo": titulo, "campos": campos}
