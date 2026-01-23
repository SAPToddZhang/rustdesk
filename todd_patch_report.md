# Todd Android Patch Report

## Targets

- old_package: `com.carriez.flutter_hbb`
- new_package: `com.celonis.work`
- old_app_name: `RustDesk`
- new_app_name: `ToddDesk`
- old_scheme: `rustdesk`
- new_scheme: `todddesk`
- old_service: `InputService`
- new_service: `ToddService`
- accessibility_desc: `Made by Todd`

## File changes

- changed_files_count: **17**
  - `flutter/android/app/build.gradle`
  - `flutter/android/app/src/profile/AndroidManifest.xml`
  - `flutter/android/app/src/debug/AndroidManifest.xml`
  - `flutter/android/app/src/main/AndroidManifest.xml`
  - `flutter/android/app/src/main/kotlin/ffi.kt`
  - `flutter/android/app/src/main/res/values/strings.xml`
  - `flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/BootReceiver.kt`
  - `flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/InputService.kt`
  - `flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/VolumeController.kt`
  - `flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/MainActivity.kt`
  - `flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/common.kt`
  - `flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/AudioRecordHandle.kt`
  - `flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/MainApplication.kt`
  - `flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/RdClipboardManager.kt`
  - `flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/FloatingWindowService.kt`
  - `flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/MainService.kt`
  - `flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/PermissionRequestTransparentActivity.kt`

## Directory move / notes

- Moved kotlin dir: /home/runner/work/rustdesk/rustdesk/flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb -> /home/runner/work/rustdesk/rustdesk/flutter/android/app/src/main/kotlin/com/celonis/work
