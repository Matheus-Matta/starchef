"""Dados variados, plausiveis e as vezes toscos — como um operador de verdade.

Nada aqui e uniforme de proposito: nome com acento, telefone com e sem
mascara, campo em branco, texto colado do WhatsApp, CAPS LOCK, espaco
sobrando. E o material bruto que o `builder` usa e o `chaos` estraga.
"""
import itertools
import random
import string
import threading
import time
import uuid

# Comeca num ponto diferente a cada processo: duas execucoes contra o MESMO
# banco nao podem repetir numero de comanda, CPF ou nome — a segunda veria
# "ja existe" em payload valido e isso viraria suspeita falsa.
_sequencia = itertools.count((int(time.time()) % 100_000) * 10_000 + 1)
_trava = threading.Lock()


def unico():
    """Contador do processo. CPF, EAN e codigo precisam ser unicos na conta:
    dois workers sorteando do mesmo espaco colidiriam e o 409 apareceria como
    se fosse defeito do backend."""
    with _trava:
        return next(_sequencia)

NOMES = ["Ana", "Bruno", "Carla", "Diego", "Eduarda", "Fabio", "Gabriela", "Henrique",
         "Isabela", "Joao", "Karina", "Lucas", "Mariana", "Nicolas", "Olivia", "Pedro",
         "Quesia", "Rafaela", "Samuel", "Tatiane", "Ubirajara", "Vinicius", "Wagner", "Yasmin"]
SOBRENOMES = ["Silva", "Souza", "Oliveira", "Santos", "Pereira", "Costa", "Almeida",
              "Ferreira", "Rodrigues", "Gomes", "Martins", "Araujo", "D'Avila", "Sao Paulo"]
PRATOS = ["X-Burger", "Picanha na Chapa", "Feijoada", "Acai 500ml", "Coxinha", "Pastel de Queijo",
          "Suco de Laranja", "Guarana Lata", "Buffet por Kg", "Pudim", "Filé à Parmegiana",
          "Escondidinho", "Baião de Dois", "Água c/ Gás", "Caipirinha", "Espetinho Misto"]
RUAS = ["Rua das Flores", "Av. Brasil", "Travessa Sao Jorge", "Alameda dos Anjos", "Rod. BR-101 km 12"]
CIDADES = [("Rio de Janeiro", "RJ"), ("Sao Paulo", "SP"), ("Belo Horizonte", "MG"), ("Recife", "PE")]
SUJEIRA = ["", "   ", "N/A", "-", "?", "aaaaaaaaaa", "teste teste", "NAO SEI", "123", "<>",
           "'; DROP TABLE orders;--", "<script>alert(1)</script>", "😀🔥 comida boa",
           "  espaco  sobrando  ", "ÇÃOÊÉÍÓÚ", "\t\ttab", "null", "undefined", "0"]


def rng(seed=None):
    return random.Random(seed)


def pessoa(r):
    return f"{r.choice(NOMES)} {r.choice(SOBRENOMES)}"


def telefone(r, limpo=True):
    ddd = r.randint(11, 99)
    numero = r.randint(900000000, 999999999)
    if not limpo:
        return str(numero)[: r.randint(3, 9)]  # incompleto, como quem desiste no meio
    forma = r.random()
    if forma < 0.4:
        return f"({ddd}) {str(numero)[:5]}-{str(numero)[5:]}"
    if forma < 0.7:
        return f"{ddd}{numero}"
    return f"+55{ddd}{numero}"


def email(r, limpo=True):
    nome = pessoa(r).lower().replace(" ", ".").replace("'", "")
    dominio = r.choice(["gmail.com", "hotmail.com", "empresa.com.br", "teste.local"])
    if not limpo:
        return r.choice([f"{nome}@@{dominio}", f"{nome} @{dominio}", nome, f"@{dominio}"])
    return f"{nome}{r.randint(1, 999)}@{dominio}"


def cpf(r, limpo=True):
    """CPF com digitos verificadores corretos e base unica no processo."""
    semente = f"{unico():09d}"[-9:]
    base = [int(d) for d in semente]
    for peso_inicial in (10, 11):
        soma = sum(v * (peso_inicial - i) for i, v in enumerate(base))
        digito = (soma * 10) % 11
        base.append(0 if digito == 10 else digito)
    numero = "".join(map(str, base))
    if not limpo:
        return numero[:-1] + str((int(numero[-1]) + 1) % 10)  # digito verificador errado
    if r.random() < 0.3:
        return f"{numero[:3]}.{numero[3:6]}.{numero[6:9]}-{numero[9:]}"
    return numero


def cnpj(r, limpo=True):
    """CNPJ com 14 digitos e verificadores corretos; base unica no processo."""
    base = [int(d) for d in f"{unico():08d}"[-8:]] + [0, 0, 0, 1]
    for pesos in ((5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2), (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)):
        soma = sum(v * p for v, p in zip(base, pesos))
        resto = soma % 11
        base.append(0 if resto < 2 else 11 - resto)
    numero = "".join(map(str, base))
    if not limpo:
        return numero[:11]  # tamanho de CPF: o erro classico de digitacao
    if r.random() < 0.3:
        return f"{numero[:2]}.{numero[2:5]}.{numero[5:8]}/{numero[8:12]}-{numero[12:]}"
    return numero


def usuario(r, limpo=True):
    """Login: so letras, numeros e @/./+/-/_ — com espaco quando desleixado."""
    nome = f"lt_{codigo(r, 6).lower()}"
    return nome if limpo else nome.replace("_", " ")


def texto(r, curto=False, limpo=True):
    if not limpo:
        return r.choice(SUJEIRA)
    partes = r.randint(1, 3 if curto else 12)
    return " ".join(r.choice(PRATOS + NOMES) for _ in range(partes)).strip()


def nome_produto(r):
    sufixo = r.choice(["", " P", " G", " Familia", f" #{r.randint(1, 9999)}", " (novo)"])
    return f"{r.choice(PRATOS)}{sufixo}"


def dinheiro(r, minimo=1, maximo=250, limpo=True):
    valor = r.uniform(minimo, maximo)
    if not limpo:
        return round(valor, 4)  # casas decimais demais, como quem cola de planilha
    return round(valor, 2)


def codigo(r, tamanho=8):
    marca = f"{unico():06d}"
    aleatorio = "".join(r.choice(string.ascii_uppercase + string.digits) for _ in range(max(tamanho - 6, 1)))
    return (aleatorio + marca)[:max(tamanho, 7)]


def ean13(r):
    """GTIN-13 com digito verificador correto (o backend confere)."""
    base = f"{789:03d}{unico():09d}"[:12]
    soma = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(base))
    return base + str((10 - soma % 10) % 10)


def endereco(r):
    cidade, uf = r.choice(CIDADES)
    return {
        "street": r.choice(RUAS),
        "number": str(r.randint(1, 4000)) if r.random() < 0.9 else "s/n",
        "district": r.choice(["Centro", "Copacabana", "Boa Viagem", ""]),
        "city": cidade,
        "state": uf,
        "zip_code": f"{r.randint(10000, 99999)}-{r.randint(100, 999)}",
        "complement": r.choice(["", "Apto 302", "fundos", "casa 2"]),
    }


def uuid4(r):
    return str(uuid.UUID(int=r.getrandbits(128), version=4))


def peso(r, limpo=True):
    """Peso de balanca: plausivel no modo limpo, absurdo no modo desleixado."""
    if not limpo:
        return round(r.uniform(60, 400), 3)
    return round(r.uniform(0.08, 2.4), 3)
