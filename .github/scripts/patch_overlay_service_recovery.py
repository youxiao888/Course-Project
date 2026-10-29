#!/usr/bin/env python3
"""OS-sticky overlay service restart: restore UI without launching main app."""
from pathlib import Path
p=Path("app/src/main/java/com/galaxy/airviewdictionary/core/OverlayService.kt")
s=p.read_text("utf8")
def one(a,b):
 global s
 if s.count(a)!=1:raise RuntimeError(f"Service anchor count {s.count(a)} {a[:130]}")
 s=s.replace(a,b,1)
one("import android.os.IBinder",'''import android.os.IBinder
import android.provider.Settings
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay''')
one('''        } catch (e: SecurityException) {
            val intent = Intent(applicationContext, SplashActivity::class.java)
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
        } catch (e: IllegalStateException) {''',
'''        } catch (e: SecurityException) {
            // Android 14+ forbids starting an unconsented media-projection FGS.
            // Do NOT unexpectedly launch the main activity from a floating tool.
            Timber.tag(TAG).w(e, "Foreground overlay service permission denied")
            stopSelf()
            return START_NOT_STICKY
        } catch (e: IllegalStateException) {''')
one('''        return START_STICKY
    }

    override fun onBind(intent: Intent): IBinder''',
'''        // After Android kills and later recreates a sticky service, the process
        // has no Compose window. Reattach the ball if overlay permission remains.
        if (intent == null && Settings.canDrawOverlays(this)) {
            lifecycleScope.launch {
                delay(700)
                if (!TargetHandleView.INSTANCE.isRunning.get()) {
                    runCatching { TargetHandleView.INSTANCE.cast(applicationContext) }
                        .onFailure { Timber.tag(TAG).w(it, "Restore floating ball failed") }
                }
            }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent): IBinder''')
p.write_text(s,"utf8")
print("sticky restart recovers lost overlay without jumping to activity")
