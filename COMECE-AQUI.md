# Comece aqui

Quatro passos. Nenhum deles exige saber programar.

## 1. Instale o Python (uma vez só)

Baixe em [python.org/downloads](https://www.python.org/downloads/).
**No Windows, marque a caixa "Add Python to PATH"** na primeira tela do instalador.

## 2. Abra o programa

Dê dois cliques em:

- **`iniciar.bat`** — Windows
- **`iniciar.command`** — Mac

Na primeira vez ele instala tudo sozinho, inclusive o navegador que conversa com
os sites dos órgãos. Leva alguns minutos e aparece uma janela preta com o
andamento — é normal. Quando terminar, o painel abre no seu navegador.

Se quiser conhecer o sistema antes de cadastrar clientes de verdade, feche essa
janela e dê dois cliques em `demonstracao.bat` (Windows) ou rode
`python -m certidoes demonstracao`: ele cria um escritório fictício com casos
variados, marcados como **sem valor legal**.

## 3. Confira as fontes

No painel, vá em **Configurações › Conferir as fontes** e clique em
**Conferir agora**.

O sistema abre cada site de órgão e verifica se ainda sabe operá-lo. **Ele não
emite nada** — para antes do botão de emissão e antes de qualquer captcha. Leva
um ou dois minutos.

No fim aparece um resultado por certidão:

- **A fonte está de pé** — o sistema consegue emitir essa certidão.
- **Precisa de ajuste** — o órgão mudou o site. Clique em **Baixar relatório** e
  envie o arquivo para quem cuida do sistema: ele traz os campos que a página tem
  hoje e o seletor de cada um, que é exatamente o que falta para consertar.

Vale repetir essa conferência sempre que uma emissão começar a falhar.

## 4. Cadastre e deixe rodar

Em **Titulares › Novo titular**, informe a pessoa ou empresa e marque quais
certidões ela precisa manter vigentes. A partir daí:

- o **Painel** mostra o que está vigente, o que vence e o que falta;
- o sistema **renova sozinho** antes do vencimento;
- quando um site pedir captcha ou login gov.br, **a tela avisa** e você responde
  ali mesmo — vários captchas seguidos, sem esperar entre um e outro;
- o botão **Dossiê**, na lista de titulares, junta todas as certidões vigentes
  num PDF único com folha de rosto — é o que a licitação pede.

---

## Perguntas rápidas

**Alguns órgãos mandam a certidão por e-mail. Para onde vai?**
Para o *E-mail do escritório*, que você define em Configurações. Em branco, vai
para o e-mail do titular.

**Onde ficam meus arquivos?**
Numa pasta só, `.certidoes` dentro da sua pasta de usuário: banco de dados, PDFs
organizados por titular e ano, e as sessões de navegador. Backup = copiar essa pasta.

**Preciso deixar o programa aberto?**
Para o sistema renovar sozinho, sim. Fechando a janela preta, ele para — o que já
foi arquivado continua lá.

**Por que a CND Federal abre no meu navegador em vez de emitir sozinha?**
Porque o portal da Receita Federal bloqueia acesso automatizado — ele diz isso
na tela. Em vez de tentar enganá-lo, o sistema abre o endereço no seu navegador,
onde o gov.br já está logado. Você emite e anexa o PDF; o controle de validade,
o nome do arquivo e o aviso de vencimento continuam iguais.

**E se eu não quiser automação nenhuma?**
Funciona igual: você anexa os PDFs que emitiu à mão e o sistema controla validade,
avisa dos vencimentos e monta o dossiê.

**Alguém de fora acessa isso?**
Não. O programa escuta só no seu computador (`127.0.0.1`). Senhas do gov.br, se
você cadastrar, ficam cifradas.
