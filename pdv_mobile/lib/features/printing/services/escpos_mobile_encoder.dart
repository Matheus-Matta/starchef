import 'dart:convert';

class EscPosMobileEncoder {
  const EscPosMobileEncoder();

  List<int> encode({
    required String text,
    String? barcode,
    bool escPos = true,
  }) {
    if (!escPos) return _plainText(text, barcode);
    final bytes = <int>[0x1b, 0x40, 0x1b, 0x74, 0x02, ..._cp850('$text\n')];
    final code = barcode?.trim() ?? '';
    if (code.isNotEmpty && code.length <= 80) {
      bytes.addAll(_code128(code));
    }
    bytes.addAll([0x0a, 0x0a, 0x0a, 0x1d, 0x56, 0x00]);
    return bytes;
  }

  List<int> _plainText(String text, String? barcode) {
    final code = barcode?.trim() ?? '';
    final fallback = code.isEmpty ? '' : '\n\nCOMANDA - CODE128 (TEXTO)\n$code';
    return utf8.encode('$text$fallback\n\n\n\n\n\n');
  }

  List<int> _code128(String value) => [
    0x1b,
    0x61,
    0x01,
    0x1d,
    0x48,
    0x02,
    0x1d,
    0x68,
    72,
    0x1d,
    0x77,
    2,
    0x1d,
    0x6b,
    73,
    value.length + 2,
    0x7b,
    0x42,
    ...ascii.encode(value),
    0x0a,
    0x1b,
    0x61,
    0x00,
  ];

  List<int> _cp850(String value) => value.runes.map((rune) {
    final mapped = _accentMap[rune];
    if (mapped != null) return mapped;
    if (rune >= 32 && rune <= 126 || rune == 10 || rune == 13) return rune;
    return 0x3f;
  }).toList();
}

const _accentMap = <int, int>{
  0x00c7: 128,
  0x00fc: 129,
  0x00e9: 130,
  0x00e2: 131,
  0x00e4: 132,
  0x00e0: 133,
  0x00e5: 134,
  0x00e7: 135,
  0x00ea: 136,
  0x00eb: 137,
  0x00e8: 138,
  0x00ef: 139,
  0x00ee: 140,
  0x00ec: 141,
  0x00c4: 142,
  0x00c5: 143,
  0x00c9: 144,
  0x00f4: 147,
  0x00f6: 148,
  0x00f2: 149,
  0x00fb: 150,
  0x00f9: 151,
  0x00d6: 153,
  0x00dc: 154,
  0x00e1: 160,
  0x00ed: 161,
  0x00f3: 162,
  0x00fa: 163,
  0x00f1: 164,
  0x00d1: 165,
  0x00ba: 167,
  0x00aa: 166,
  0x00e3: 198,
  0x00c3: 199,
  0x00f5: 228,
  0x00d5: 229,
};
