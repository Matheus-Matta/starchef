import base64
import hashlib
import xml.etree.ElementTree as ET
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography import x509

NFE_NS = "http://www.portalfiscal.inf.br/nfe"
XMLDSIG_NS = "http://www.w3.org/2000/09/xmldsig#"


def validate_key_and_certificate(private_key, certificate) -> None:
    """
    Valida se a chave privada e o certificado público pertencem exatamente
    ao mesmo par criptográfico RSA antes da assinatura.
    """
    if not private_key or not certificate:
        raise ValueError("Chave privada ou certificado não fornecidos.")

    cert_pub_numbers = certificate.public_key().public_numbers()
    key_pub_numbers = private_key.public_key().public_numbers()

    if cert_pub_numbers != key_pub_numbers:
        raise ValueError("A chave privada e o certificado X.509 não pertencem ao mesmo par criptográfico.")


def canonicalize_xml_str(xml_str: str) -> str:
    """
    Canonicalização W3C C14N 1.0 rigorosa (REC-xml-c14n-20010315) sem comentários
    utilizando a biblioteca padrão do Python (ET.canonicalize).
    Garante conformidade com o padrão XMLDSig da NF-e sem dependências externas.
    """
    return ET.canonicalize(xml_str)


def validate_no_forbidden_prefixes(xml_str_or_bytes) -> None:
    """
    Validação de segurança contra a Rejeição 404 da SEFAZ:
    'Rejeicao: Uso de prefixo de namespace nao permitido'

    A área de dados fiscal da NF-e e a assinatura digital devem utilizar
    os namespaces padrão sem qualquer prefixo (ex: ns0:, nfe:, ds:).
    """
    text = xml_str_or_bytes.decode("utf-8") if isinstance(xml_str_or_bytes, bytes) else str(xml_str_or_bytes)
    forbidden = [
        "<ns0:", "</ns0:",
        "<nfe:", "</nfe:",
        "<ds:", "</ds:",
        "xmlns:ns0=", "xmlns:nfe=", "xmlns:ds="
    ]
    found = [val for val in forbidden if val in text]
    if found:
        raise ValueError(
            f"XML fiscal contém prefixos de namespace proibidos pela SEFAZ: {found}. "
            "A área fiscal deve utilizar o namespace padrão da NF-e e XMLDSig sem prefixos."
        )


def sign_xml_node(root_element_or_xml, target_node_tag: str, reference_id: str, private_key, certificate) -> str:
    """
    Assina digitalmente o nó target_node_tag (ex: infEvento) dentro de root_element_or_xml
    segundo o padrão W3C XMLDSig exigido pela SEFAZ:
    - Sem uso de prefixo ds:
    - C14N 1.0 (REC-xml-c14n-20010315)
    - RSA-SHA1 (PKCS#1 v1.5)
    - DigestMethod SHA-1
    - Transforms: enveloped-signature e C14N 1.0
    - Retorna a string XML completa assinada
    """
    validate_key_and_certificate(private_key, certificate)

    if isinstance(root_element_or_xml, bytes):
        xml_str = root_element_or_xml.decode("utf-8")
    elif isinstance(root_element_or_xml, str):
        xml_str = root_element_or_xml
    elif hasattr(root_element_or_xml, "tag"):
        xml_str = ET.tostring(root_element_or_xml, encoding="utf-8").decode("utf-8")
    else:
        raise TypeError(f"Tipo de XML não suportado para assinatura: {type(root_element_or_xml)}")

    # 1. Localizar infEvento no XML
    start_tag = f'<{target_node_tag} '
    end_tag = f'</{target_node_tag}>'
    start_idx = xml_str.find(start_tag)
    end_idx = xml_str.find(end_tag, start_idx)
    if start_idx == -1 or end_idx == -1:
        raise ValueError(f"Nó {target_node_tag} não encontrado no XML.")

    target_content = xml_str[start_idx:end_idx + len(end_tag)]
    if f'Id="{reference_id}"' not in target_content:
        raise ValueError(f"Nó {target_node_tag} com Id='{reference_id}' não encontrado.")

    # Canonicalização C14N 1.0 de infEvento com namespace herdado da NF-e
    target_for_c14n = target_content
    if f'xmlns="{NFE_NS}"' not in target_for_c14n:
        target_for_c14n = target_for_c14n.replace(f'<{target_node_tag} ', f'<{target_node_tag} xmlns="{NFE_NS}" ', 1)

    target_c14n = canonicalize_xml_str(target_for_c14n)
    target_digest = base64.b64encode(hashlib.sha1(target_c14n.encode("utf-8")).digest()).decode("ascii")

    # 2. Montar SignedInfo rigorosamente no padrão XMLDSig da NF-e sem prefixo ds:
    signed_info_xml = (
        f'<SignedInfo xmlns="{XMLDSIG_NS}">'
        f'<CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>'
        f'<SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"/>'
        f'<Reference URI="#{reference_id}">'
        f'<Transforms>'
        f'<Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>'
        f'<Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>'
        f'</Transforms>'
        f'<DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/>'
        f'<DigestValue>{target_digest}</DigestValue>'
        f'</Reference>'
        f'</SignedInfo>'
    )
    signed_info_c14n = canonicalize_xml_str(signed_info_xml)

    # 3. Assinar com RSA-SHA1 (PKCS#1 v1.5)
    signature_bytes = private_key.sign(
        signed_info_c14n.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA1()
    )
    signature_value = base64.b64encode(signature_bytes).decode("ascii")

    # 4. Certificado X.509 em formato DER (Base64) — apenas o certificado da empresa, sem cadeia
    cert_der = certificate.public_bytes(serialization.Encoding.DER)
    cert_b64 = base64.b64encode(cert_der).decode("ascii")

    # 5. Montar nó Signature completo no namespace padrão XMLDSig
    signature_xml = (
        f'<Signature xmlns="{XMLDSIG_NS}">'
        f'{signed_info_xml}'
        f'<SignatureValue>{signature_value}</SignatureValue>'
        f'<KeyInfo>'
        f'<X509Data>'
        f'<X509Certificate>{cert_b64}</X509Certificate>'
        f'</X509Data>'
        f'</KeyInfo>'
        f'</Signature>'
    )

    # 6. Inserir Signature no parent (<evento>) após </infEvento>
    evento_close = "</evento>"
    if evento_close in xml_str:
        final_xml = xml_str.replace(evento_close, f"{signature_xml}{evento_close}", 1)
    else:
        final_xml = xml_str + signature_xml

    return final_xml


def verify_xml_signature(xml_content) -> bool:
    """
    Verificação local obrigatória da assinatura do XML antes do envio para a SEFAZ:
    1. Confere se Id de infEvento coincide com Reference/@URI.
    2. Recalcula o C14N 1.0 e o SHA-1 de infEvento e valida o DigestValue.
    3. Recalcula o C14N 1.0 de SignedInfo.
    4. Valida a assinatura RSA-SHA1 de SignedInfo usando a chave pública contida no X509Certificate.
    5. Dispara ValueError detalhado se qualquer divergência for detectada.
    """
    text = xml_content.decode("utf-8") if isinstance(xml_content, bytes) else str(xml_content)
    root = ET.fromstring(text)
    namespaces = {
        'nfe': NFE_NS,
        'ds': XMLDSIG_NS,
    }

    inf_elem = root.find('.//nfe:infEvento', namespaces)
    if inf_elem is None:
        raise ValueError("Elemento infEvento não encontrado no XML.")

    ref_id = inf_elem.get("Id")
    if not ref_id or not ref_id.startswith("ID"):
        raise ValueError(f"Atributo Id do infEvento inválido ou ausente: {ref_id}")

    ref_elem = root.find('.//ds:Reference', namespaces)
    if ref_elem is None:
        raise ValueError("Elemento Reference não encontrado em Signature.")

    expected_uri = f"#{ref_id}"
    if ref_elem.get("URI") != expected_uri:
        raise ValueError(f"Reference URI ({ref_elem.get('URI')}) não coincide com o Id do infEvento ({expected_uri})")

    # 1. Validar DigestValue
    digest_elem = root.find('.//ds:DigestValue', namespaces)
    if digest_elem is None or not digest_elem.text:
        raise ValueError("DigestValue ausente no XML.")
    xml_digest = digest_elem.text.strip()

    start_tag = '<infEvento'
    end_tag = '</infEvento>'
    s_idx = text.find(start_tag)
    e_idx = text.find(end_tag, s_idx)
    inf_sub = text[s_idx:e_idx + len(end_tag)]
    if f'xmlns="{NFE_NS}"' not in inf_sub:
        inf_sub = inf_sub.replace('<infEvento', f'<infEvento xmlns="{NFE_NS}"', 1)

    inf_c14n = canonicalize_xml_str(inf_sub)
    calc_digest = base64.b64encode(hashlib.sha1(inf_c14n.encode("utf-8")).digest()).decode("ascii")

    if xml_digest != calc_digest:
        raise ValueError(f"DigestValue inválido! Calculado: {calc_digest} != XML: {xml_digest}")

    # 2. Validar SignedInfo e SignatureValue
    si_start = text.find('<SignedInfo')
    si_end = text.find('</SignedInfo>')
    if si_start == -1 or si_end == -1:
        raise ValueError("SignedInfo ausente no XML.")
    si_sub = text[si_start:si_end + len('</SignedInfo>')]
    if f'xmlns="{XMLDSIG_NS}"' not in si_sub:
        si_sub = si_sub.replace('<SignedInfo', f'<SignedInfo xmlns="{XMLDSIG_NS}"', 1)

    signed_info_c14n = canonicalize_xml_str(si_sub)

    sig_val_elem = root.find('.//ds:SignatureValue', namespaces)
    if sig_val_elem is None or not sig_val_elem.text:
        raise ValueError("SignatureValue ausente no XML.")
    sig_bytes = base64.b64decode(sig_val_elem.text.strip())

    cert_elem = root.find('.//ds:X509Certificate', namespaces)
    if cert_elem is None or not cert_elem.text:
        raise ValueError("X509Certificate ausente no XML.")
    cert_der = base64.b64decode(cert_elem.text.strip())
    cert_obj = x509.load_der_x509_certificate(cert_der)

    pub_key = cert_obj.public_key()
    pub_key.verify(
        sig_bytes,
        signed_info_c14n.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA1()
    )
    return True
