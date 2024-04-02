def soma_e_media(numeros):
    # Verifica se a lista está vazia
    if not numeros:
        return 0, 0

    # Calcula a soma
    soma = sum(numeros)
    
    # Calcula a média
    media = soma / len(numeros)
    
    return soma, media

# Exemplo de uso
lista_de_numeros = [1, 2, 3, 4]
soma, media = soma_e_media(lista_de_numeros)
print(f"Soma: {soma}, Média: {media}")

##############################################################################

def substituir_palavra(lista_palavras, palavra_procurada, nova_palavra):
 
  lista_alterada = []
  for palavra in lista_palavras:
    if palavra == palavra_procurada:
      lista_alterada.append(nova_palavra)
    else:
      lista_alterada.append(palavra)
  return lista_alterada

# Exemplo de uso
lista_palavras = ["banana", "morango", "limão", 
                  "cereja", "abacaxi", "laranja"]
palavra_procurada = "banana"
nova_palavra = "maçã"

lista_alterada = substituir_palavra(lista_palavras, 
                                    palavra_procurada, nova_palavra)

print(f"Lista original: {lista_palavras}")
print(f"Palavra procurada: {palavra_procurada}")
print(f"Nova palavra: {nova_palavra}")
print(f"Lista alterada: {lista_alterada}")

###############################################################################

def gerar_triangulo(n):
    for i in range(1, n + 1):
        print('*' * i)

# Exemplo de uso
gerar_triangulo(6)


