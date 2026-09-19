import requests
from typing import Optional
from datetime import datetime
from dataclasses import dataclass, field
from apps.inbound_nfe.services.certificate import get_certificate_paths, cleanup_temp_files
import xml.etree.ElementTree as ET
import base64
import gzip
import logging

logger = logging.getLogger(__name__)


@dataclass
class DFeDocument:
    """Representa um documento individual extraído de um docZip da SEFAZ."""
    nsu: str
    schema: str
    xml: str


@dataclass
class DistDFeResponse:
    cstat: str
    reason: str
    ult_nsu: Optional[str]   # None se ausente na resposta — NUNCA sobrescrever NSU salvo com None
    max_nsu: Optional[str]   # None se ausente na resposta
    dh_resp: Optional[datetime] = None  # Data/hora da resposta da SEFAZ
    documents: list[DFeDocument] = field(default_factory=list)


class NFeDistribuicaoClient:

    URLS = {
        'production': 'https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx',
        'homologation': 'https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx'
    }

    def __init__(self, account, restaurant_id=None, environment: str = "production"):
        self.account = account
        self.restaurant_id = restaurant_id
        self.environment = environment
        self.url = self.URLS.get(environment, self.URLS['production'])

    def _build_soap_request(self, uf_code: str, cnpj: str, ult_nsu: str) -> str:
        amb = "1" if self.environment == "production" else "2"
        return f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Body>
    <nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
      <nfeDadosMsg>
        <distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
          <tpAmb>{amb}</tpAmb>
          <cUFAutor>{uf_code}</cUFAutor>
          <CNPJ>{cnpj}</CNPJ>
          <distNSU>
            <ultNSU>{ult_nsu.zfill(15)}</ultNSU>
          </distNSU>
        </distDFeInt>
      </nfeDadosMsg>
    </nfeDistDFeInteresse>
  </soap12:Body>
</soap12:Envelope>"""

    def fetch_since_nsu(self, cnpj: str, uf_code: str, ult_nsu: str) -> DistDFeResponse:
        cert_paths = None
        try:
            cert_paths = get_certificate_paths(self.account, restaurant_id=self.restaurant_id)
            cert_path, key_path = cert_paths

            payload = self._build_soap_request(uf_code, cnpj, ult_nsu)
            headers = {
                'Content-Type': 'application/soap+xml; charset=utf-8',
            }

            logger.info(
                f"SEFAZ distNSU: cnpj={cnpj}, uf={uf_code}, "
                f"ult_nsu={ult_nsu}, env={self.environment}"
            )

            response = requests.post(
                self.url,
                data=payload,
                headers=headers,
                cert=(cert_path, key_path),
                timeout=30
            )

            response.raise_for_status()
            return self._parse_soap_response(response.text)

        finally:
            if cert_paths:
                cleanup_temp_files(cert_paths[0], cert_paths[1])

    def _build_cons_nsu_request(self, uf_code: str, cnpj: str, nsu: str) -> str:
        amb = "1" if self.environment == "production" else "2"
        return f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Body>
    <nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
      <nfeDadosMsg>
        <distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
          <tpAmb>{amb}</tpAmb>
          <cUFAutor>{uf_code}</cUFAutor>
          <CNPJ>{cnpj}</CNPJ>
          <consNSU>
            <NSU>{nsu.zfill(15)}</NSU>
          </consNSU>
        </distDFeInt>
      </nfeDadosMsg>
    </nfeDistDFeInteresse>
  </soap12:Body>
</soap12:Envelope>"""

    def fetch_nsu(self, cnpj: str, uf_code: str, nsu: str) -> DistDFeResponse:
        """
        Consulta pontual de um documento específico por NSU via consNSU.
        Atenção: A SEFAZ limita consNSU a 20 consultas por hora para o CNPJ.
        """
        cert_paths = None
        try:
            cert_paths = get_certificate_paths(self.account, restaurant_id=self.restaurant_id)
            cert_path, key_path = cert_paths

            payload = self._build_cons_nsu_request(uf_code, cnpj, nsu)
            headers = {
                'Content-Type': 'application/soap+xml; charset=utf-8',
            }

            logger.info(
                f"SEFAZ consNSU: cnpj={cnpj}, uf={uf_code}, "
                f"nsu={nsu}, env={self.environment}"
            )

            response = requests.post(
                self.url,
                data=payload,
                headers=headers,
                cert=(cert_path, key_path),
                timeout=30
            )

            response.raise_for_status()
            return self._parse_soap_response(response.text)

        finally:
            if cert_paths:
                cleanup_temp_files(cert_paths[0], cert_paths[1])

    def _build_cons_chnfe_request(self, uf_code: str, cnpj: str, access_key: str) -> str:
        amb = "1" if self.environment == "production" else "2"
        return f"""<?xml version="1.0" encoding="utf-8"?>
<soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
  <soap12:Body>
    <nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">
      <nfeDadosMsg>
        <distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
          <tpAmb>{amb}</tpAmb>
          <cUFAutor>{uf_code}</cUFAutor>
          <CNPJ>{cnpj}</CNPJ>
          <consChNFe>
            <chNFe>{access_key.strip()}</chNFe>
          </consChNFe>
        </distDFeInt>
      </nfeDadosMsg>
    </nfeDistDFeInteresse>
  </soap12:Body>
</soap12:Envelope>"""

    def fetch_by_access_key(self, cnpj: str, uf_code: str, access_key: str) -> DistDFeResponse:
        """
        Consulta direta de uma NF-e específica pela chave de acesso via consChNFe.
        Usado após a Ciência da Operação para obter o procNFe_v4.00.xsd com os produtos.
        Atenção: consChNFe NUNCA altera o last_nsu da conta/restaurante.
        """
        cert_paths = None
        try:
            cert_paths = get_certificate_paths(self.account, restaurant_id=self.restaurant_id)
            cert_path, key_path = cert_paths

            payload = self._build_cons_chnfe_request(uf_code, cnpj, access_key)
            headers = {
                'Content-Type': 'application/soap+xml; charset=utf-8',
            }

            logger.info(
                f"SEFAZ consChNFe: cnpj={cnpj}, uf={uf_code}, "
                f"access_key={access_key}, env={self.environment}"
            )

            response = requests.post(
                self.url,
                data=payload,
                headers=headers,
                cert=(cert_path, key_path),
                timeout=30
            )

            response.raise_for_status()
            return self._parse_soap_response(response.text)

        finally:
            if cert_paths:
                cleanup_temp_files(cert_paths[0], cert_paths[1])

    def _parse_soap_response(self, xml_text: str) -> DistDFeResponse:
        root = ET.fromstring(xml_text)

        namespaces = {
            'soap': 'http://www.w3.org/2003/05/soap-envelope',
            'nfe': 'http://www.portalfiscal.inf.br/nfe'
        }

        cstat = root.find('.//nfe:cStat', namespaces)
        reason = root.find('.//nfe:xMotivo', namespaces)
        ret_ult_nsu = root.find('.//nfe:ultNSU', namespaces)
        max_nsu = root.find('.//nfe:maxNSU', namespaces)
        dh_resp_el = root.find('.//nfe:dhResp', namespaces)

        cstat_val = cstat.text if cstat is not None else ""
        reason_val = reason.text if reason is not None else ""
        # PONTO 2: Retornar None quando ausente, NUNCA "000000000000000"
        ult_val = ret_ult_nsu.text if ret_ult_nsu is not None else None
        max_val = max_nsu.text if max_nsu is not None else None

        dh_resp_val = None
        if dh_resp_el is not None and dh_resp_el.text:
            try:
                dh_resp_val = datetime.fromisoformat(dh_resp_el.text)
            except Exception:
                pass

        docs = []
        lote = root.find('.//nfe:loteDistDFeInt', namespaces)
        if lote is not None:
            for docZip in lote.findall('nfe:docZip', namespaces):
                # PONTO 3: Capturar NSU e schema de cada docZip
                doc_nsu = docZip.attrib.get('NSU', '')
                doc_schema = docZip.attrib.get('schema', '')
                compressed_b64 = docZip.text
                if compressed_b64:
                    try:
                        compressed = base64.b64decode(compressed_b64)
                        xml_bytes = gzip.decompress(compressed)
                        xml_str = xml_bytes.decode('utf-8')
                        docs.append(DFeDocument(
                            nsu=doc_nsu,
                            schema=doc_schema,
                            xml=xml_str,
                        ))
                    except Exception as e:
                        logger.error(
                            f"Erro ao descompactar docZip NSU={doc_nsu}: {e}"
                        )

        logger.info(
            f"SEFAZ resposta: cStat={cstat_val}, "
            f"ultNSU={ult_val}, maxNSU={max_val}, "
            f"dhResp={dh_resp_val}, docs={len(docs)}"
        )

        return DistDFeResponse(
            cstat=cstat_val,
            reason=reason_val,
            ult_nsu=ult_val,
            max_nsu=max_val,
            dh_resp=dh_resp_val,
            documents=docs
        )
