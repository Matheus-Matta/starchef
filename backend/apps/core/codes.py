"""Geração de QR Code e código de barras (Code128) como PNG data-URI.

Usado por comandas e mesas (payload escaneável no PDV). As dependências são
importadas de forma best-effort: se a lib faltar, retorna "" em vez de quebrar
(mesmo padrão do QR do cupom fiscal em apps/invoices/services.py).
"""
import base64
import io


def qr_data_uri(data):
    """QR Code do `data` como PNG data-URI. Vazio se sem dado/lib."""
    if not data:
        return ""
    try:
        import qrcode

        buffer = io.BytesIO()
        qrcode.make(str(data)).save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        return ""


def barcode_data_uri(data):
    """Código de barras Code128 do `data` como PNG data-URI. Vazio se sem dado/lib."""
    if not data:
        return ""
    try:
        import barcode
        from barcode.writer import ImageWriter

        buffer = io.BytesIO()
        code128 = barcode.get("code128", str(data), writer=ImageWriter())
        # sem texto embaixo (o número é exibido à parte na folha/etiqueta)
        code128.write(buffer, options={"write_text": False, "module_height": 12.0})
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        return ""
