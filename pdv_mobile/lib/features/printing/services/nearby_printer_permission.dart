import 'dart:io';

import 'package:flutter/services.dart';

class NearbyPrinterPermission {
  const NearbyPrinterPermission();

  static const _channel = MethodChannel(
    'br.com.starchef.pdv_mobile/nearby_permission',
  );

  Future<bool> request() async {
    if (!Platform.isAndroid) return true;
    return await _channel.invokeMethod<bool>('request') ?? false;
  }

  Future<void> openSettings() async {
    if (!Platform.isAndroid) return;
    await _channel.invokeMethod<void>('openSettings');
  }
}
