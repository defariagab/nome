# Nome: Alice - Idade: 25 - Cidade: São Paulo!
def questao1(nome, idade, cidade):
    print("Nome", nome, sep=": ", end=" - ")
    print("Idade", idade, sep=": ", end=" - ")
    print("Cidade", cidade, sep=": ", end="!\n")   
    
questao1('Gabriel', 25, "Rio de Janeiro")
questao1('José', 20, "Niterói")

def questao2():
    n1 = float(input("Entre com o primeiro número:"))
    n2 = float(input("Entre com o segundo número:"))
    op = input("Entre com a operação (+, -, *, ou /):")
    
    if op == '+':
        r = n1 + n2
    elif op == '-':
        r = n1 - n2
    elif op == '*':
        r = n1 * n2
    elif op == '/':
        r = n1 / n2
    else:
        r = "operador desconhecido"
    
    print("resultado:", r)
    
questao2()

def questao3():
    texto = input("Digite os itens da lista de compras separados por vírgulas:")
    lista = texto.split(',')
    
    contador = 1
    for item in lista:
        print("Item ", contador, ": ", item, sep='')
        contador += 1
    
questao3()  

def questao4():
    celsius_texto = input("Entre com a temperatura em Celsius: ")
    celsius = float(celsius_texto)

    f = (celsius * 9/5) + 32
    print("A temperatura em Fahrenheit é", f)    
    
questao4()

def questao5():
    print("Entre com nomes. Digite sair para terminar. ")
    nomes = []
    
    while True:
        entrada = input()
        if entrada.lower() == 'sair':
            break
        else:
            nomes.append(entrada)

    for nome in nomes:
        print(nome)
    
questao5()
    
    
    
    
    
    
    