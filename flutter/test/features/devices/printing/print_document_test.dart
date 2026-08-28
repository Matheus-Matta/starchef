import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/devices/printing/print_document.dart';

void main() {
  group('Code128 payload', () {
    test('extracts Code128 only from payload version 2', () {
      expect(
        PrintDocument.code128ValueFromPayload({
          'payload_version': 2,
          'barcode': {'symbology': 'code128', 'value': ' CMD-1042 '},
        }),
        'CMD-1042',
      );
      expect(
        PrintDocument.code128ValueFromPayload({
          'payload_version': 1,
          'barcode': {'symbology': 'CODE128', 'value': 'CMD-1042'},
        }),
        isNull,
      );
      expect(
        PrintDocument.code128ValueFromPayload({
          'payload_version': 2,
          'barcode': {'symbology': 'QR', 'value': 'CMD-1042'},
        }),
        isNull,
      );
      expect(
        PrintDocument.code128ValueFromPayload({
          'payload_version': 2,
          'barcode': {'symbology': 'CODE128', 'value': '   '},
        }),
        isNull,
      );
    });
  });

  group('QR payload (DANFE NFC-e)', () {
    test('extracts qr_data only from payload version 2', () {
      expect(
        PrintDocument.qrValueFromPayload({
          'payload_version': 2,
          'qr_data': ' https://sefaz.sp.gov.br/nfce?p=abc ',
        }),
        'https://sefaz.sp.gov.br/nfce?p=abc',
      );
      expect(
        PrintDocument.qrValueFromPayload({
          'payload_version': 1,
          'qr_data': 'https://sefaz.sp.gov.br/nfce?p=abc',
        }),
        isNull,
      );
      expect(
        PrintDocument.qrValueFromPayload({
          'payload_version': 2,
          'qr_data': '   ',
        }),
        isNull,
      );
      expect(
        PrintDocument.qrValueFromPayload({'payload_version': 2}),
        isNull,
      );
    });
  });

  group('conversão de HTML para texto (último recurso)', () {
    test(
      'não gruda rótulo e valor quando a linha de tabela vem compacta',
      () {
        // POST /orders/{id}/print/ não devolve text_content — só html — e o
        // template Django escreve a linha de subtotal numa única linha de
        // código-fonte, sem espaço nenhum entre as tags.
        const html =
            '<table><tr><td>Subtotal</td><td>R\$ 237,00</td></tr></table>';
        expect(
          PrintDocument.htmlToText(html),
          'Subtotal  R\$ 237,00',
        );
      },
    );

    test(
      'produz o mesmo resultado independente da indentação do HTML de origem',
      () {
        // A mesma linha, mas quebrada em várias linhas de código-fonte (como
        // o bloco de itens do template) — antes disso produzia uma quebra de
        // linha diferente da versão compacta, um acidente de formatação.
        const html = '<table>\n  <tr>\n    <td>1 x xtudo</td>\n'
            '    <td>R\$ 49,00</td>\n  </tr>\n</table>';
        expect(
          PrintDocument.htmlToText(html),
          '1 x xtudo  R\$ 49,00',
        );
      },
    );

    test('remove CSS/JS e normaliza entidades comuns', () {
      const html =
          '<style>td{padding:2px}</style><p>Ol&aacute; &amp; adeus</p>';
      expect(
        PrintDocument.htmlToText(html),
        'Ol&aacute; & adeus',
      );
    });
  });
}
