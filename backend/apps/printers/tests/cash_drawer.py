"""O corpo de cadastro compartilhado pelos testes da gaveta.

Nao e um arquivo de teste: o pytest nao coleta nada daqui. Existe para os tres
arquivos da gaveta partirem da MESMA impressora, e uma mudanca no cadastro
minimo nao precisar ser repetida em tres lugares.
"""


def printer_payload_body(restaurant, **overrides):
    body = {
        "name": "Caixa 01",
        "restaurant": str(restaurant.id),
        "driver_type": "escpos",
        "connection_type": "network",
        "host": "192.168.10.50",
        "port": 9100,
        "timeout_seconds": 10,
    }
    body.update(overrides)
    return body
