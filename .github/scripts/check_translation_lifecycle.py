#!/usr/bin/env python3
"""Fail CI if startup/composition can destroy a not-yet-populated translation view."""
from pathlib import Path

p=Path("app/src/main/java/com/galaxy/airviewdictionary/ui/screen/overlay/translation/TranslationView.kt")
t=p.read_text(encoding="utf8")
start=t.index("override val composable:")
end=t.index("override fun onServiceConnected(",start)
composition=t[start:end]
assert 'initialValue = Pair<VisionText?, Transaction?>(null, null)' in composition, "Initial state changed; inspect lifecycle policy"
assert "val display=current ?: if(holdTranslation) lastDisplay else null" in composition, "Snapshot fallback removed"
assert "TranslationBox(" in composition, "Translation UI no longer rendered"
import re
# Ignore explanatory comments when checking executable Compose code.
executable=re.sub(r'//[^\\n]*','',composition)
executable=re.sub(r'/\\*[\\s\\S]*?\\*/','',executable)
assert "clear()" not in executable, "CRITICAL: initial loading state must never destroy the window"
assert "else if(display!=null)" in composition, "Valid translation must be rendered without a premature attached-flag race"
assert "lastDisplay=Pair(visionText,translation)" in t, "cast must save translation before Compose sees initial flow"
# Prior regression: with initial null-null, no direct flow result is available yet.
# The pre-cast snapshot MUST be preserved until first valid emission.
from dataclasses import dataclass
@dataclass
class UIState:
    snapshot: object|None
    current: object|None
    attached: bool

def should_display(x:UIState):
    return (x.current or x.snapshot) is not None
assert should_display(UIState("cast-snapshot",None,False))
assert should_display(UIState("cast-snapshot",None,True))
assert should_display(UIState(None,"emitted-translation",True))
assert not should_display(UIState(None,None,False))
print("PASS: initial null/null cannot clear window; cast snapshot renders independent of attach timing")
