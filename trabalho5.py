def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr

def print_vowels(text):
    vowels = "aeiouAEIOU"
    vowels_in_text = [char for char in text if char in vowels]
    return ' '.join(vowels_in_text)

# Testando o Bubble Sort
lista_exemplo = [14, 3, 16, 9, 22, 11, 90]
lista_ordem = bubble_sort(lista_exemplo)

# Testando a impressão de vogais
frase = "Trabalho 5"
vogais_na_frase = print_vowels(frase)

lista_ordem, vogais_na_frase
