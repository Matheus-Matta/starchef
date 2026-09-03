import unittest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from apps.inbound_nfe.services.sefaz_client import DistDFeResponse, DFeDocument
from apps.inbound_nfe.services.xml_parser import (
    DOC_RES_NFE,
    DOC_PROC_NFE,
    detect_document_type,
)


class SyncLogicTestCase(unittest.TestCase):
    def test_dfe_document_dataclass(self):
        doc = DFeDocument(
            nsu="000000000000010",
            schema="resNFe_v1.01.xsd",
            xml="<resNFe>...</resNFe>"
        )
        self.assertEqual(doc.nsu, "000000000000010")
        self.assertEqual(doc.schema, "resNFe_v1.01.xsd")
        self.assertEqual(doc.xml, "<resNFe>...</resNFe>")

    def test_dist_dfe_response_handles_none_nsu(self):
        # PONTO 2: ult_nsu e max_nsu podem ser None sem quebrar
        resp = DistDFeResponse(
            cstat="137",
            reason="Nenhum documento localizado",
            ult_nsu=None,
            max_nsu=None,
            documents=[],
        )
        self.assertEqual(resp.cstat, "137")
        self.assertIsNone(resp.ult_nsu)
        self.assertIsNone(resp.max_nsu)
        self.assertEqual(len(resp.documents), 0)

    def test_dist_dfe_response_with_documents(self):
        docs = [
            DFeDocument(nsu="000000000000001", schema="resNFe_v1.01.xsd", xml="<resNFe/>"),
            DFeDocument(nsu="000000000000002", schema="procNFe_v4.00.xsd", xml="<nfeProc/>"),
        ]
        resp = DistDFeResponse(
            cstat="138",
            reason="Documento(s) localizado(s)",
            ult_nsu="000000000000002",
            max_nsu="000000000000005",
            documents=docs,
        )
        self.assertEqual(resp.cstat, "138")
        self.assertEqual(resp.ult_nsu, "000000000000002")
        self.assertEqual(resp.max_nsu, "000000000000005")
        self.assertEqual(len(resp.documents), 2)
        self.assertEqual(detect_document_type(resp.documents[0].schema), DOC_RES_NFE)
        self.assertEqual(detect_document_type(resp.documents[1].schema), DOC_PROC_NFE)

    def test_cstat_656_with_dh_resp_and_nsu(self):
        from datetime import datetime
        resp = DistDFeResponse(
            cstat="656",
            reason="Rejeicao: Consumo Indevido (Deve ser utilizado o ultNSU nas solicitacoes subsequentes. Tente apos 1 hora)",
            ult_nsu="000000000000050",
            max_nsu="000000000000000",
            dh_resp=datetime.fromisoformat("2026-09-01T14:27:49-03:00"),
            documents=[],
        )
        self.assertEqual(resp.cstat, "656")
        self.assertEqual(resp.ult_nsu, "000000000000050")
        self.assertIsNotNone(resp.dh_resp)
        self.assertEqual(resp.dh_resp.hour, 14)
        self.assertEqual(resp.dh_resp.minute, 27)
