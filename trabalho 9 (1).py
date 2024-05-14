def gravar_nome_em_arquivo():
    nome = input("Digite seu nome: ")
    
    # Abrir o arquivo em modo de escrita ('w')
    with open("nomes.txt", "w") as arquivo:
        # Escrever o nome no arquivo
        arquivo.write(nome)
    
    print("Nome gravado com sucesso no arquivo 'nomes.txt'.")
    
def imprimir_conteudo_arquivo():
    # Pedir ao usuário o nome do arquivo de texto
    nome_arquivo = input("Digite o nome do arquivo de texto: ")
    
    # Abrir o arquivo em modo de leitura ('r')
    with open(nome_arquivo, "r") as arquivo:
        # Ler e imprimir o conteúdo do arquivo
        conteudo = arquivo.read()
        print("Conteúdo do arquivo:")
        print(conteudo)

def copiar_arquivo(origem, destino):
    # Abrir o arquivo de origem em modo de leitura ('r')
    with open(origem, "r") as arquivo_origem:
        # Ler o conteúdo do arquivo de origem
        conteudo = arquivo_origem.read()
    
    # Abrir o arquivo de destino em modo de escrita ('w')
    with open(destino, "w") as arquivo_destino:
        # Escrever o conteúdo no arquivo de destino
        arquivo_destino.write(conteudo)
    
    print(f"Conteúdo do arquivo '{origem}' copiado com sucesso para '{destino}'.")

def encontrar_nome_por_numero(numero, arquivo):
    # Abrir o arquivo em modo de leitura ('r')
    with open(arquivo, "r") as arquivo_exemplo:
        # Percorrer cada linha do arquivo
        for linha in arquivo_exemplo:
            # Dividir a linha em partes separadas por espaço
            partes = linha.split()
            # Verificar se o primeiro elemento é igual ao número fornecido
            if partes[0] == str(numero):
                # Se sim, imprimir o nome correspondente
                print("Nome correspondente ao número", numero, ":", partes[1])
                # Retornar para evitar a verificação desnecessária
                return
    
    # Se o número não for encontrado, imprimir uma mensagem de erro
    print("Número não encontrado no arquivo.")