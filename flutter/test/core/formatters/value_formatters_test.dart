import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/formatters/value_formatters.dart';

void main() {
  group('number', () {
    test('aceita num, string com ponto e string com vírgula', () {
      expect(ValueFormatters.number(12.5), 12.5);
      expect(ValueFormatters.number('12.5'), 12.5);
      expect(ValueFormatters.number('12,5'), 12.5);
      expect(ValueFormatters.number(' 12.5 '), 12.5);
    });

    test('devolve zero para valor ausente ou ilegível', () {
      expect(ValueFormatters.number(null), 0);
      expect(ValueFormatters.number(''), 0);
      expect(ValueFormatters.number('abc'), 0);
    });
  });

  group('optionalNumber', () {
    test('distingue ausência de zero', () {
      expect(ValueFormatters.optionalNumber(null), isNull);
      expect(ValueFormatters.optionalNumber(''), isNull);
      expect(ValueFormatters.optionalNumber(0), 0);
      expect(ValueFormatters.optionalNumber('0'), 0);
    });
  });

  test('integer usa o fallback quando o valor não serve', () {
    expect(ValueFormatters.integer(9100), 9100);
    expect(ValueFormatters.integer('9100'), 9100);
    expect(ValueFormatters.integer(null, fallback: 9600), 9600);
    expect(ValueFormatters.integer('x', fallback: 3), 3);
  });

  test('money usa o formato brasileiro', () {
    expect(ValueFormatters.money(1234.5), r'R$ 1234,50');
    expect(ValueFormatters.money('0'), r'R$ 0,00');
    expect(ValueFormatters.money(null), r'R$ 0,00');
  });

  test('weight usa as três casas das balanças', () {
    expect(ValueFormatters.weight(1.25), '1,250 kg');
    expect(ValueFormatters.weight('0.5'), '0,500 kg');
  });

  group('nullableId', () {
    test('trata as três formas de relacionamento vazio', () {
      expect(ValueFormatters.nullableId(null), isNull);
      expect(ValueFormatters.nullableId(''), isNull);
      expect(ValueFormatters.nullableId('   '), isNull);
      // A API pode serializar um vínculo ausente como a string "null".
      expect(ValueFormatters.nullableId('null'), isNull);
    });

    test('preserva um identificador real', () {
      expect(
        ValueFormatters.nullableId(' 8f14e45f-ceea-4a12 '),
        '8f14e45f-ceea-4a12',
      );
    });
  });
}
