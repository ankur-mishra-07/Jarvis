# iOS app

This directory holds the SwiftUI shell. The Xcode project file
(`iosApp.xcodeproj`) is **not** committed — generate it locally so it picks up
your developer team and signing identity:

```
cd mobile
./gradlew :shared:linkDebugFrameworkIosSimulatorArm64
open iosApp/iosApp/JarvisApp.swift
```

In Xcode:

1. Create a new **iOS App** project at `mobile/iosApp/` named `iosApp`,
   bundle id e.g. `com.jarvis.app`.
2. Add the existing files (`JarvisApp.swift`, `ContentView.swift`).
3. Add the KMP framework: *Build Phases → Link Binary With Libraries* →
   add `shared.framework` produced by Gradle in
   `shared/build/bin/iosSimulatorArm64/debugFramework/`.
4. Add **Privacy — Microphone Usage Description** to `Info.plist`.
5. Add `BASE_URL` and `API_KEY` to `Info.plist` from `Config.xcconfig`.
6. Add the `audio` Background Mode capability.

The wake-word and on-device audio I/O are stubbed in
`shared/iosMain/.../*.ios.kt`; replace with Porcupine iOS SDK + AVAudioEngine.
