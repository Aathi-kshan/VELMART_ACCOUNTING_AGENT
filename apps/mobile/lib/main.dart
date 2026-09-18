import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Keep the red-screen / console dump. Do not swallow — web async errors
  // that skip FlutterError.onError would otherwise only hit the browser
  // console and can look like a blank canvas.
  FlutterError.onError = (details) {
    FlutterError.dumpErrorToConsole(details);
    FlutterError.presentError(details);
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    FlutterError.dumpErrorToConsole(
      FlutterErrorDetails(exception: error, stack: stack),
    );
    return true;
  };
  runApp(const ProviderScope(child: VelmartApp()));
}
