import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/features/menu/domain/product_options.dart';

void main() {
  test('usa logo_p antes do campo legado', () {
    expect(
      productImageUrl({
        'logo_p': 'https://cdn.test/profile.jpg',
        'image': 'https://cdn.test/legacy.jpg',
      }),
      'https://cdn.test/profile.jpg',
    );
  });

  test('ignora photo_list porque o app usa apenas a foto de perfil', () {
    expect(
      productImageUrl({
        'photo_list': [
          {'url': 'https://cdn.test/other.png'},
          {'url': 'https://cdn.test/primary.png', 'is_primary': true},
        ],
      }),
      '',
    );
  });
}
