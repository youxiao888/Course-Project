#!/usr/bin/env python3
"""Incremental changes only: strict word/gap hit testing; optional no-edge-docking."""
from pathlib import Path
root=Path(".")
base=Path("app/src/main/java/com/galaxy/airviewdictionary")
def change(p, old, new):
    p=root/p
    v=p.read_text(encoding="utf8")
    n=v.count(old)
    if n!=1:
        raise RuntimeError(f"{p}: expected 1 match, got {n}: {old[:130]!r}")
    p.write_text(v.replace(old,new,1),encoding="utf8")
    print("updated",p)

geom=base/"ui/screen/overlay/targethandle/PreciseWordHit.kt"
geom.write_text("""package com.galaxy.airviewdictionary.ui.screen.overlay.targethandle

/**
 * Pure geometry, independent of Android framework: a point belongs to a word
 * only when it lies INSIDE that word's recognized box. Never extend boxes
 * into the inter-word space, even for very narrow words.
 */
internal object PreciseWordHit {
    fun contains(
        x: Int, y: Int,
        left: Int, top: Int, right: Int, bottom: Int,
        margin: Int
    ): Boolean {
        val width = right - left
        val height = bottom - top
        if (width <= 0 || height <= 0) return false
        // Keep the center selectable for narrow glyphs.
        val mx = minOf(margin.coerceAtLeast(0), (width - 1) / 4)
        val my = minOf(margin.coerceAtLeast(0), (height - 1) / 4)
        return x >= left + mx && x < right - mx &&
               y >= top + my && y < bottom - my
    }
}
""",encoding="utf8")

vm=str(base/"ui/screen/overlay/targethandle/TargetHandleViewModel.kt")
old="""            val word = getPointerPositionedVisionText(visionResult, pointerPosition, TextDetectMode.WORD)
            if (word is Word &&
                word.representation.trim().isNotEmpty() &&
                word.representation.trim().length <= 40 &&
                !word.representation.any { it.isWhitespace() } &&
                expandedRect(word.boundingBox).contains(pointerPosition.x, pointerPosition.y)
            ) {
                Timber.tag(TAG).d("SmartHover: word selected: ${word.representation}")
                return word
            }"""
new="""            // Read the paragraph via the same cache used by normal target selection.
            // Examine ALL word boxes; do not select the nearest word or use an
            // expanded hitbox, which incorrectly eats the space between words.
            val paragraph = visionResult.paragraphs.firstOrNull {
                it.boundingBox.contains(pointerPosition.x, pointerPosition.y)
            }?.let { readParagraph(visionResult, it) }

            val inset = 1.dp.toPx(applicationContext)
            val wordsUnderPointer = paragraph?.lines.orEmpty()
                .flatMap { it.words }
                .filter { word ->
                    val box = word.boundingBox
                    PreciseWordHit.contains(
                        pointerPosition.x, pointerPosition.y,
                        box.left, box.top, box.right, box.bottom, inset
                    ) &&
                    word.representation.trim().isNotEmpty() &&
                    word.representation.trim().length <= 40 &&
                    word.representation.none { it.isWhitespace() }
                }
            // Exactly one matched word is required; overlap/ambiguity and whitespace
            // both keep the sentence or paragraph that the user selected.
            if (wordsUnderPointer.size == 1) {
                val word = wordsUnderPointer.single()
                Timber.tag(TAG).d("SmartHover precise word: ${word.representation}")
                return word
            }
            Timber.tag(TAG).d("SmartHover gap/overlap: normal sentence or paragraph")"""
change(vm,old,new)
# Persistent separate toggle; preserving the existing delay slider and its behavior
pref=str(base/"data/local/preference/PreferenceRepository.kt")
change(pref,
       '        val DRAG_HANDLE_DOCKING = booleanPreferencesKey("drag_handle_docking")',
       '        val DRAG_HANDLE_DOCKING = booleanPreferencesKey("drag_handle_docking")\n        val NO_EDGE_DOCKING = booleanPreferencesKey("no_edge_docking")')
change(pref,
       '    val dragHandleDockingFlow: Flow<Boolean> = preferenceFlow.map { preferences ->',
       '    val noEdgeDockingFlow: Flow<Boolean> = preferenceFlow.map { preferences ->\n        preferences[NO_EDGE_DOCKING] ?: false\n    }\n\n    val dragHandleDockingFlow: Flow<Boolean> = preferenceFlow.map { preferences ->')

settingsvm=str(base/"ui/screen/main/SettingsViewModel.kt")
change(settingsvm,
       '    fun updateDragHandleDocking(dragHandleDocking: Boolean) {',
       '    fun updateNoEdgeDocking(value: Boolean) {\n        preferenceRepository.update(PreferenceRepository.NO_EDGE_DOCKING, value)\n    }\n\n    fun updateDragHandleDocking(dragHandleDocking: Boolean) {')

settings=str(base/"ui/screen/main/SettingsActivity.kt")
change(settings,
       '        // Haptic feedback to detection\n        val dragHandleHaptic',
       '        val noEdgeDocking by viewModel.preferenceRepository.noEdgeDockingFlow.collectAsStateWithLifecycle(\n            lifecycle = lifecycleOwner.lifecycle,\n            initialValue = false\n        )\n\n        // Haptic feedback to detection\n        val dragHandleHaptic')
change(settings,
       '''                            MenuItem(
                                menuItemPosition = MenuItemPosition.Bottom,
                                onClick = {
                                    if (!dragHandleHaptic) {''',
       '''                            // New independent toggle: does not change docking delay slider.
                            MenuItem(
                                menuItemPosition = MenuItemPosition.Middle,
                                onClick = { viewModel.updateNoEdgeDocking(!noEdgeDocking) }
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.SpaceBetween
                                ) {
                                    MenuRowText(text = getString(R.string.settings_no_edge_docking))
                                    Switch(
                                        checked = noEdgeDocking,
                                        onCheckedChange = { viewModel.updateNoEdgeDocking(it) },
                                        colors = SwitchDefaults.colors(
                                            checkedThumbColor = switchThumbColor,
                                            checkedTrackColor = switchTrackColor
                                        ),
                                        modifier = Modifier
                                            .scale(switchScale)
                                            .semantics {
                                                contentDescription = if (noEdgeDocking) "No edge docking on" else "No edge docking off"
                                            }
                                    )
                                }
                            }

                            MenuItem(
                                menuItemPosition = MenuItemPosition.Bottom,
                                onClick = {
                                    if (!dragHandleHaptic) {''')
for folder,label in [
    ("values","Keep floating ball in place (disable edge docking)"),
    ("values-zh-rCN","悬浮球不吸边"),
    ("values-zh-rTW","懸浮球不吸邊")
]:
    change(f"app/src/main/res/{folder}/strings.xml","</resources>",
          f'    <string name="settings_no_edge_docking">{label}</string>\n</resources>')

handle=str(base/"ui/screen/overlay/targethandle/TargetHandleView.kt")
change(handle,
       '        val dragHandleHaptic by viewModel.preferenceRepository.dragHandleHapticFlow.collectAsStateWithLifecycle(',
       '''        val noEdgeDocking by viewModel.preferenceRepository.noEdgeDockingFlow.collectAsStateWithLifecycle(
            lifecycle = lifecycleOwner.lifecycle,
            initialValue = false
        )
        // If toggled on while already docked, bring the existing handle back into view.
        LaunchedEffect(noEdgeDocking) {
            if (noEdgeDocking) {
                cancelDockDragHandle()
                if (isAttachedToWindow()) repositionWithinScreen(context)
            }
        }
        val dragHandleHaptic by viewModel.preferenceRepository.dragHandleHapticFlow.collectAsStateWithLifecycle(''')
change(handle,
       '        LaunchedEffect(motionEventState, translationState, menuOperatingState) {',
       '        LaunchedEffect(motionEventState, translationState, menuOperatingState, noEdgeDocking) {')
change(handle,
       '''            if (menuOperatingState) {
                cancelDockDragHandle()
            } else {
                // ACTION_CANCEL''',
       '''            if (noEdgeDocking || menuOperatingState) {
                cancelDockDragHandle()
            } else {
                // ACTION_CANCEL''')
# guard a separate automatic call outside the regular Compose docking branch
change(handle,
       '''            Event.DockTargetHandleView -> {
                dockDragHandle(overlayService.applicationContext, true)
            }''',
       '''            Event.DockTargetHandleView -> {
                if (!noEdgeDockingEnabled()) dockDragHandle(overlayService.applicationContext, true)
            }''')
change(handle,
       '''    private fun scheduleDockDragHandle(context: Context, start: Boolean, delay: Long) {''',
       '''    private fun noEdgeDockingEnabled(): Boolean =
        viewModel.preferenceRepository.noEdgeDockingFlowValue()

    private fun scheduleDockDragHandle(context: Context, start: Boolean, delay: Long) {''')
# Avoid introducing blocking flow API; use live synchronized setting updated by a collection.
# Move noEdgeDockingEnabled to a member kept in sync with composable.
change(handle,
       '''    private fun noEdgeDockingEnabled(): Boolean =
        viewModel.preferenceRepository.noEdgeDockingFlowValue()''',
       '''    @Volatile private var noEdgeDockingEnabled = false

    private fun noEdgeDockingEnabled(): Boolean = noEdgeDockingEnabled''')
change(handle,
       '''        LaunchedEffect(noEdgeDocking) {
            if (noEdgeDocking) {''',
       '''        LaunchedEffect(noEdgeDocking) {
            noEdgeDockingEnabled = noEdgeDocking
            if (noEdgeDocking) {''')
change(handle,
       '''    private fun scheduleDockDragHandle(context: Context, start: Boolean, delay: Long) {
        dragHandleDockingJob?.cancel()''',
       '''    private fun scheduleDockDragHandle(context: Context, start: Boolean, delay: Long) {
        if (noEdgeDockingEnabled()) return
        dragHandleDockingJob?.cancel()''')
change(handle,
       '''    private fun dockDragHandle(context: Context, start: Boolean) {
        Timber.tag(TAG).d("#### dockDragHandle() ####")''',
       '''    private fun dockDragHandle(context: Context, start: Boolean) {
        if (noEdgeDockingEnabled()) return
        Timber.tag(TAG).d("#### dockDragHandle() ####")''')
# User changes preference in settings while overlays are not composed? ViewModel preference state
# is updated on next compose. The handle always collects noEdgeDocking flow.

# Pure JVM unit tests: these run on CI, not merely hypothetical.
test=root/"app/src/test/java/com/galaxy/airviewdictionary/ui/screen/overlay/targethandle/PreciseWordHitTest.kt"
test.parent.mkdir(parents=True,exist_ok=True)
test.write_text("""package com.galaxy.airviewdictionary.ui.screen.overlay.targethandle

import org.junit.Assert.*
import org.junit.Test

class PreciseWordHitTest {
    @Test fun centerOfWordMatches() {
        assertTrue(PreciseWordHit.contains(15, 12, 10, 8, 20, 18, 1))
    }
    @Test fun gapBetweenTwoWordsNeverMatches() {
        val x=25
        assertFalse(PreciseWordHit.contains(x, 12, 10, 8, 20, 18, 1))
        assertFalse(PreciseWordHit.contains(x, 12, 30, 8, 40, 18, 1))
    }
    @Test fun wordEdgesDoNotStealGap() {
        assertFalse(PreciseWordHit.contains(20, 12, 10, 8, 20, 18, 1))
        assertFalse(PreciseWordHit.contains(30, 12, 30, 8, 40, 18, 1))
    }
    @Test fun thinWordsStillSelectable() {
        assertTrue(PreciseWordHit.contains(10, 11, 10, 8, 11, 15, 1))
    }
    @Test fun wrongRowAndEmptyBoxNeverMatch() {
        assertFalse(PreciseWordHit.contains(15, 22, 10, 8, 20, 18, 1))
        assertFalse(PreciseWordHit.contains(15, 12, 10, 8, 10, 18, 1))
    }
}
""",encoding="utf8")
print("Precise hover geometry + independent no-edge docking switch patch succeeded.")
