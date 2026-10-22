#!/usr/bin/env python3
"""Small opt-in accessibility screenshot and two-stage word-hover extension."""
from pathlib import Path

root = Path(".")
base = Path("app/src/main/java/com/galaxy/airviewdictionary")

def change(path, old, new):
    path = root / path
    source = path.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise RuntimeError(f"{path}: expected exactly one match, got {source.count(old)}: {old[:100]!r}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")
    print("patched", path)

service = base / "data/local/capture/OcrScreenshotAccessibilityService.kt"
service.write_text(r'''package com.galaxy.airviewdictionary.data.local.capture

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.os.Build
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.resume

/**
 * Explicitly opt-in via Android's Accessibility settings once.
 * Screenshot only, never reads accessibility node contents or performs gestures.
 */
class OcrScreenshotAccessibilityService : AccessibilityService() {
    companion object {
        @Volatile private var connected: OcrScreenshotAccessibilityService? = null
        val isConnected: Boolean get() = connected != null

        suspend fun screenshot(): Bitmap? {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return null
            val service = connected ?: return null
            return withTimeoutOrNull(2500L) {
                suspendCancellableCoroutine { continuation ->
                    try {
                        service.takeScreenshot(Display.DEFAULT_DISPLAY, service.mainExecutor,
                            object : TakeScreenshotCallback {
                                override fun onSuccess(screenshot: ScreenshotResult) {
                                    try {
                                        val hardwareBuffer = screenshot.hardwareBuffer
                                        val bitmap = try {
                                            Bitmap.wrapHardwareBuffer(hardwareBuffer, screenshot.colorSpace)
                                                ?.copy(Bitmap.Config.ARGB_8888, false)
                                        } finally {
                                            hardwareBuffer.close()
                                        }
                                        if (continuation.isActive) continuation.resume(bitmap)
                                    } catch (_: Exception) {
                                        if (continuation.isActive) continuation.resume(null)
                                    }
                                }
                                override fun onFailure(errorCode: Int) {
                                    if (continuation.isActive) continuation.resume(null)
                                }
                            })
                    } catch (_: Exception) {
                        if (continuation.isActive) continuation.resume(null)
                    }
                }
            }
        }
    }
    override fun onServiceConnected() {
        super.onServiceConnected()
        connected = this
    }
    override fun onAccessibilityEvent(event: AccessibilityEvent?) = Unit
    override fun onInterrupt() = Unit
    override fun onDestroy() {
        if (connected === this) connected = null
        super.onDestroy()
    }
}
''', encoding="utf-8")

accessibility_xml = root / "app/src/main/res/xml/ocr_screenshot_accessibility.xml"
accessibility_xml.write_text('''<?xml version="1.0" encoding="utf-8"?>
<accessibility-service xmlns:android="http://schemas.android.com/apk/res/android"
    android:accessibilityEventTypes="typeWindowStateChanged"
    android:accessibilityFeedbackType="feedbackGeneric"
    android:notificationTimeout="0"
    android:canRetrieveWindowContent="false"
    android:canTakeScreenshot="true"
    android:description="@string/ocr_screenshot_service_description" />
''', encoding="utf-8")

change("app/src/main/res/values/strings.xml",
       "</resources>",
       '    <string name="ocr_screenshot_service_description">Take screenshots for on-screen OCR after you enable this accessibility service once. No window text or gestures are accessed.</string>\n</resources>')

change("app/src/main/AndroidManifest.xml",
       '        <service\n            android:name=".core.OverlayService"',
       '''        <service
            android:name=".data.local.capture.OcrScreenshotAccessibilityService"
            android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"
            android:exported="true"
            android:label="@string/app_name">
            <intent-filter>
                <action android:name="android.accessibilityservice.AccessibilityService" />
            </intent-filter>
            <meta-data
                android:name="android.accessibilityservice"
                android:resource="@xml/ocr_screenshot_accessibility" />
        </service>

        <service
            android:name=".core.OverlayService"''')

capture = base / "data/local/capture/CaptureRepository.kt"
change(str(capture),
       '        captureResponseFlow.value = null\n\n        Timber.tag(TAG).i("State $state")',
       '''        // If the user enabled the optional screenshot accessibility service, do not
        // request a new MediaProjection session or show the OS consent dialog.
        // When disabled, preserve the original capture path. When enabled,
        // transient screenshot errors should NOT reopen the OS consent dialog.
        if (OcrScreenshotAccessibilityService.isConnected) {
            val screenshot = OcrScreenshotAccessibilityService.screenshot()
            return if (screenshot != null) {
                CaptureResponse.Success(removeAlphaChannel(screenshot))
            } else {
                CaptureResponse.Error(CapturedImageInvalidException())
            }
        }

        captureResponseFlow.value = null

        Timber.tag(TAG).i("State $state")''')

vm = str(base / "ui/screen/overlay/targethandle/TargetHandleViewModel.kt")

change(vm,
       'import kotlinx.coroutines.withContext\n',
       'import kotlinx.coroutines.withContext\nimport kotlinx.coroutines.withTimeoutOrNull\n')

change(vm,
       '    private val POINTER_STOPPED_MARGIN_DISTANCE: Int =',
       '''    // Normal sentence/paragraph hover is unchanged. An additional long dwell
    // over a recognized *word* switches only that target to word translation.
    private val WORD_HOVER_DWELL_MS = 2200L
    private val wordHoverOverrideFlow = MutableStateFlow<Point?>(null)

    private val POINTER_STOPPED_MARGIN_DISTANCE: Int =''')

change(vm,
       '        var timerJob: Job? = null\n\n        // Helper function to calculate distance',
       '''        var timerJob: Job? = null
        var wordDwellJob: Job? = null

        // Helper function to calculate distance''')

change(vm,
       '''                    if (isNotDuplicate) {
                        send(currentPoint) // Emit the position using `send`
                        lastEmittedPoint = currentPoint // Update the last emitted point
                    }''',
       '''                    if (isNotDuplicate) {
                        wordDwellJob?.cancel()
                        wordHoverOverrideFlow.value = null
                        send(currentPoint) // Original quick sentence/paragraph target
                        lastEmittedPoint = currentPoint
                        if (textDetectMode == TextDetectMode.SENTENCE ||
                            textDetectMode == TextDetectMode.PARAGRAPH
                        ) {
                            wordDwellJob = launch {
                                delay(WORD_HOVER_DWELL_MS)
                                // Wait for the ordinary target selection to occur first.
                                // For slow OCR there is no premature word-only translation.
                                withTimeoutOrNull(5000L) {
                                    currentTargetFlow.filterNotNull().first { target ->
                                        target.visionText.boundingBox.contains(currentPoint.x, currentPoint.y)
                                    }
                                } ?: return@launch
                                if (motionEventFlow.value == MotionEvent.ACTION_DOWN ||
                                    motionEventFlow.value == MotionEvent.ACTION_MOVE
                                ) {
                                    wordHoverOverrideFlow.value = currentPoint
                                }
                            }
                        }
                    }''')

change(vm,
       '''                        cancelTimer() // Cancel the ongoing timer
                        _pointerPosition = null // Reset the pointer position
                        send(null) // Emit null using `send`''',
       '''                        cancelTimer() // Cancel the ongoing timer
                        wordDwellJob?.cancel()
                        wordHoverOverrideFlow.value = null
                        _pointerPosition = null // Reset the pointer position
                        send(null) // Emit null using `send`''')

change(vm,
       '''                cancelTimer() // Cancel the timer when pointer is invalid
                _pointerPosition = null''',
       '''                cancelTimer() // Cancel the timer when pointer is invalid
                wordDwellJob?.cancel()
                wordHoverOverrideFlow.value = null
                _pointerPosition = null''')

change(vm,
       '''        val visionResult: VisionResult?,
    )''',
       '''        val visionResult: VisionResult?,
        val wordHoverOverride: Boolean,
    )''')

change(vm,
       '''        visionResultFlow,
        ocrRunningFlow,
    ) { pointerStoppedPosition, visionResult, ocrRunning ->''',
       '''        visionResultFlow,
        ocrRunningFlow,
        wordHoverOverrideFlow,
    ) { pointerStoppedPosition, visionResult, ocrRunning, wordOverride ->''')

change(vm,
       '''            visionResult != null -> LookupInput(stoppedPosition, visionResult)
            ocrRunning -> LookupInput(stoppedPosition, null)''',
       '''            visionResult != null -> LookupInput(stoppedPosition, visionResult, wordOverride == stoppedPosition)
            ocrRunning -> LookupInput(stoppedPosition, null, false)''')

change(vm,
       '''old?.position == new?.position && old?.visionResult === new?.visionResult''',
       '''old?.position == new?.position && old?.visionResult === new?.visionResult && old?.wordHoverOverride == new?.wordHoverOverride''')

change(vm,
       '''                            getPointerPositionedVisionText(
                                visionResult = visionResult,
                                pointerPosition = input.position,
                                textDetectMode = textDetectMode
                            ),''',
       '''                            findHoverTarget(
                                visionResult = visionResult,
                                pointerPosition = input.position,
                                wordHoverOverride = input.wordHoverOverride,
                            ),''')

change(vm,
       '''    /** 포인터가 머무는 위치의 VisionText. 그 자리에 글이 없으면 null. */
    val pointerPositionedVisionTextFlow''',
       '''    /**
     * Only override the normal sentence/paragraph target when the long-hover
     * point lies inside one real OCR word. No change to image translation,
     * selection mode, or empty-space behavior.
     */
    private suspend fun findHoverTarget(
        visionResult: VisionResult,
        pointerPosition: Point,
        wordHoverOverride: Boolean,
    ): VisionText? {
        if (wordHoverOverride &&
            (textDetectMode == TextDetectMode.SENTENCE || textDetectMode == TextDetectMode.PARAGRAPH) &&
            visionResult.image == null
        ) {
            val word = getPointerPositionedVisionText(visionResult, pointerPosition, TextDetectMode.WORD)
            if (word is Word && word.representation.isNotBlank() &&
                word.boundingBox.contains(pointerPosition.x, pointerPosition.y) &&
                word.representation.trim().split(Regex("\\\\s+")).size == 1
            ) return word
        }
        return getPointerPositionedVisionText(visionResult, pointerPosition, textDetectMode)
    }

    /** 포인터가 머무는 위치의 VisionText. 그 자리에 글이 없으면 null. */
    val pointerPositionedVisionTextFlow''')

change(vm,
       '''                            || movedWithinImageTarget(last, lookup)''',
       '''                            || movedWithinImageTarget(last, lookup)
                            || (wordHoverOverrideFlow.value != null &&
                                lookup.visionText is Word && last?.visionText !is Word)''')

print("Accessibility screenshot and adaptive long-hover patches passed.")
