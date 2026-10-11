# Comunicador ACBrLib

Serviço sem estado que o backend chama para assinar e transmitir NFC-e/NF-e
pela ACBrLib. Arquitetura, contrato, contingência e homologação:
[`docs/FISCAL_ACBRLIB.md`](../docs/FISCAL_ACBRLIB.md).

```bash
# desenvolvimento, com a SEFAZ simulada
ACBR_SIMULADOR=1 ACBRLIB_TOKEN=dev uvicorn app.main:app --port 8001
# testes
pytest tests
```

Em produção a `libacbrnfe64.so` (Projeto ACBr) é montada em `/app/libs`; sem
ela e sem `ACBR_SIMULADOR=1` o serviço não sobe.
