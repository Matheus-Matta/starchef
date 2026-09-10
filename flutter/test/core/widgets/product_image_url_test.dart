import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/widgets/product_image_url.dart';

void main() {
  test('prefere logo_p ao campo legado', () {
    final url = productImageUrl({
      'logo_p': 'https://cdn.test/logo.jpg',
      'image': 'https://cdn.test/legacy.jpg',
    });

    expect(url, 'https://cdn.test/logo.jpg');
  });

  test('ignora photo_list e usa somente o perfil ou o legado', () {
    expect(
      productImageUrl({
        'photo_list': [
          {'url': 'https://cdn.test/primary.png', 'is_primary': true},
        ],
      }),
      '',
    );
    expect(
      productImageUrl({'image': 'https://cdn.test/legacy.jpg'}),
      'https://cdn.test/legacy.jpg',
    );
  });
}
