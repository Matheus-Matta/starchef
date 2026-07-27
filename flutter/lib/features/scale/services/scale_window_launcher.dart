import 'dart:io';

/// Opens each quick-scale workstation as an independent desktop process.
///
/// A process-per-window keeps focus, lifecycle and crashes isolated and allows
/// any number of workstations. Authentication remains in the OS secure store;
/// no access token is exposed through command-line arguments.
abstract final class ScaleWindowLauncher {
  static const modeArgument = '--scale-workstation';

  static Future<bool> open({String? restaurantId}) async {
    if (!Platform.isWindows && !Platform.isLinux && !Platform.isMacOS) {
      return false;
    }
    final executable = Platform.resolvedExecutable;
    if (executable.trim().isEmpty) return false;
    final arguments = <String>[
      modeArgument,
      if (restaurantId != null && restaurantId.trim().isNotEmpty)
        '--restaurant=${restaurantId.trim()}',
    ];
    try {
      await Process.start(
        executable,
        arguments,
        mode: ProcessStartMode.detached,
        runInShell: false,
      );
      return true;
    } on ProcessException {
      return false;
    }
  }

  static bool isScaleWindow(List<String> arguments) =>
      arguments.contains(modeArgument);

  static String? restaurantFrom(List<String> arguments) {
    const prefix = '--restaurant=';
    for (final argument in arguments) {
      if (argument.startsWith(prefix)) {
        final value = argument.substring(prefix.length).trim();
        if (value.isNotEmpty) return value;
      }
    }
    return null;
  }
}
