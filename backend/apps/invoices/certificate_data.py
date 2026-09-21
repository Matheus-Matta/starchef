import base64


def read_certificate_bytes(config):
    """Lê o A1 canônico, seja pelo storage atual ou pela referência legada."""
    if config.certificate_file:
        config.certificate_file.open("rb")
        try:
            return config.certificate_file.read()
        finally:
            config.certificate_file.close()
    if config.certificate_ref:
        with open(config.certificate_ref, "rb") as certificate:
            return certificate.read()
    return b""


def certificate_base64(config):
    content = read_certificate_bytes(config)
    return base64.b64encode(content).decode() if content else ""
