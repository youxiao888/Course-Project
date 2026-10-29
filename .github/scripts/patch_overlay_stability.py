#!/usr/bin/env python3
"""Small overlay stability, precise touch target and draggable translation window patch."""
from pathlib import Path
root=Path(".")
base=Path("app/src/main/java/com/galaxy/airviewdictionary")
def edit(path,old,new):
 p=root/path
 t=p.read_text("utf8"); n=t.count(old)
 if n!=1: raise RuntimeError(f"{path} match {n} {old[:100]}")
 p.write_text(t.replace(old,new,1),"utf8"); print("patched",path)
def splice(path,start,end,replacement):
 p=root/path
 t=p.read_text("utf8")
 if t.count(start)!=1 or t.count(end)!=1: raise RuntimeError(f"{path} anchor not unique")
 a=t.index(start);b=t.index(end,a)
 p.write_text(t[:a]+replacement+t[b:],"utf8"); print("spliced",path)

handle=str(base/"ui/screen/overlay/targethandle/TargetHandleView.kt")
edit(handle,"import android.view.MotionEvent","import android.view.MotionEvent\nimport android.widget.ImageView")
edit(handle,"    private var viewHeight = 0","""    private var viewHeight = 0
    // The visual aiming pointer lives in a separate NOT_TOUCHABLE overlay.
    // This avoids a tall invisible touch rectangle above the ball.
    private var aimView: ImageView? = null
    private var aimParams: WindowManager.LayoutParams? = null

    private fun showAim(context: Context, centerX: Int, centerY: Int) {
        val size = pointerDimen
        if (size <= 0) return
        val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val p = aimParams ?: WindowManager.LayoutParams(
            size, size, centerX - size/2, centerY - size/2,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT
        ).apply { gravity = Gravity.TOP or Gravity.START }.also { aimParams = it }
        p.x = centerX - size/2
        p.y = centerY - size/2
        try {
            if (aimView == null) {
                aimView = ImageView(context).apply {
                    setImageResource(R.drawable.drag_pointer)
                    scaleType = ImageView.ScaleType.FIT_CENTER
                }
                wm.addView(aimView, p)
            } else {
                aimView?.visibility = View.VISIBLE
                aimView?.let { wm.updateViewLayout(it,p) }
            }
        } catch (e: Exception) {
            Timber.tag(TAG).w(e,"aim overlay update")
            removeAim(context)
        }
    }

    private fun hideAim() { aimView?.visibility = View.GONE }
    private fun removeAim(context: Context) {
        aimView?.let {
            try { (context.getSystemService(Context.WINDOW_SERVICE) as WindowManager).removeView(it) }
            catch (_: Exception) {}
        }
        aimView = null
        aimParams = null
    }

    private fun clampBall(context: Context) {
        if (!::layoutParams.isInitialized) return
        val screen = ScreenInfoHolder.get()
        if (screen.width <= 0 || screen.height <= 0) return
        val margin = 2.dp.toPx(context)
        layoutParams.x = layoutParams.x.coerceIn(margin, (screen.width-viewWidth-margin).coerceAtLeast(margin))
        layoutParams.y = layoutParams.y.coerceIn(margin, (screen.height-viewHeight-margin).coerceAtLeast(margin))
        updateLayout(context)
    }
""")
edit(handle,
"""        val motionEventState by viewModel.motionEventFlow.collectAsStateWithLifecycle()""",
"""        val motionEventState by viewModel.motionEventFlow.collectAsStateWithLifecycle()
        LaunchedEffect(captureStatus, motionEventState) {
            if (captureStatus == CaptureStatus.Requested ||
                (motionEventState != MotionEvent.ACTION_DOWN && motionEventState != MotionEvent.ACTION_MOVE)
            ) {
                hideAim()
            } else {
                viewModel.pointerPositionFlow.value?.let { showAim(context,it.x,it.y) }
            }
        }""")
splice(handle,"        Column(\n            modifier = Modifier\n                .wrapContentSize()", "        // 핸들 도킹",
"""        // The actual overlay window and touch target are only as large as
        // the floating ball. The aiming pointer is drawn by a non-touchable window.
        Box(
            modifier = Modifier
                .size(dimensionResource(R.dimen.target_handle_width))
                .alpha(if (captureStatus == CaptureStatus.Requested ||
                    (textDetectMode == TextDetectMode.FIXED_AREA && fixedAreaViewState == FixedAreaView.State.Translating)
                ) 0.01f else 1.0f),
            contentAlignment = Alignment.Center
        ) {
            val alpha by rememberInfiniteTransition(label = "service live anim").animateFloat(
                initialValue = 1.0f, targetValue = 0.9f,
                animationSpec = infiniteRepeatable(
                    animation = tween(durationMillis = 800, easing = LinearEasing),
                    repeatMode = RepeatMode.Reverse
                ), label = "service live anim spec"
            )
            Image(
                painter = painterResource(id = if (isDarkMode) R.drawable.drag_handle_dark else R.drawable.drag_handle),
                contentDescription = "Screen Translator floating ball",
                modifier = Modifier.size(dimensionResource(R.dimen.target_handle_thumb_dimen)).alpha(alpha)
            )
        }

""")
edit(handle,"""            override fun onTouch(v: View, event: MotionEvent): Boolean {
                tapDetector.onTouchEvent(event)""",
"""            override fun onTouch(v: View, event: MotionEvent): Boolean {
                // Ignore touches outside the visible circular ball, including
                // the transparent corners of this small square window.
                if (event.actionMasked == MotionEvent.ACTION_DOWN) {
                    val center = viewWidth / 2f
                    val radius = applicationContext.resources.getDimensionPixelSize(R.dimen.target_handle_thumb_dimen)/2f +
                        3.dp.toPx(applicationContext)
                    val dx = event.x-center
                    val dy = event.y-center
                    if (dx*dx+dy*dy > radius*radius) return false
                }
                tapDetector.onTouchEvent(event)""")
edit(handle,"""                    MotionEvent.ACTION_MOVE -> {
                        val screenInfo: ScreenInfo = ScreenInfoHolder.get()
                        layoutParams.x = (dragStartX + (event.rawX - touchStartX)).toInt()
                        layoutParams.y = (dragStartY + (event.rawY - touchStartY)).toInt()
                        updateLayout(applicationContext)""",
"""                    MotionEvent.ACTION_MOVE -> {
                        val screenInfo: ScreenInfo = ScreenInfoHolder.get()
                        layoutParams.x = (dragStartX + (event.rawX - touchStartX)).toInt()
                        layoutParams.y = (dragStartY + (event.rawY - touchStartY)).toInt()
                        if (noEdgeDockingEnabled()) clampBall(applicationContext)
                        else updateLayout(applicationContext)""")
edit(handle,"""                        val x = layoutParams.x + viewWidth / 2 + _pointerOffsetX
                        val y = layoutParams.y + pointerDimen / 2 + _pointerOffsetY
                        viewModel.pointerPositionFlow.value = Point(x, y)""",
"""                        val x = layoutParams.x + viewWidth / 2 + _pointerOffsetX
                        val y = layoutParams.y - pointerDimen/2 -
                            applicationContext.resources.getDimensionPixelSize(R.dimen.target_handle_pointer_thumb_space) + _pointerOffsetY
                        if (viewModel.captureStatusFlow.value != CaptureStatus.Requested) {
                            showAim(applicationContext,x,y)
                        } else {
                            hideAim()
                        }
                        viewModel.pointerPositionFlow.value = Point(x, y)""")
edit(handle,"""                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                        repositionWithinScreen(applicationContext)
                    }""",
"""                    MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                        hideAim()
                        if (noEdgeDockingEnabled()) clampBall(applicationContext)
                        else repositionWithinScreen(applicationContext)
                    }""")
edit(handle,"""        viewHeight = applicationContext.resources.getDimensionPixelSize(R.dimen.target_handle_height)""",
"""        viewHeight = applicationContext.resources.getDimensionPixelSize(R.dimen.target_handle_width)""")
edit(handle,"""            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            screenInfo.width / 2 - viewWidth / 2,""",
"""            viewWidth,
            viewHeight,
            screenInfo.width / 2 - viewWidth / 2,""")
edit(handle,"""                    or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                    or WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,""",
"""                    or WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,""")
edit(handle,"""    override fun clear() {
        dragHandleDockingJob?.cancel()
        super.clear()""",
"""    override fun clear() {
        dragHandleDockingJob?.cancel()
        hideAim()
        if (isServiceInitialized()) {
            view?.context?.let { removeAim(it.applicationContext) }
        }
        super.clear()""")
# Replace buggy spring-driven reposition for non-docking mode:
edit(handle,"""    private fun repositionWithinScreen(applicationContext: Context) {
        val screenInfo: ScreenInfo = ScreenInfoHolder.get()""",
"""    private fun repositionWithinScreen(applicationContext: Context) {
        if (noEdgeDockingEnabled()) {
            clampBall(applicationContext)
            return
        }
        val screenInfo: ScreenInfo = ScreenInfoHolder.get()""")
# For rotation, always restore ball safely; old rotation calculation remains.
edit(handle,"""        updateLayout(context)
        Timber.tag(TAG).d("updateLayout layoutParams.x""",
"""        clampBall(context)
        Timber.tag(TAG).d("updateLayout layoutParams.x""")

# Add draggable handle inside existing footer: no gestures in translation text itself.
trans=str(base/"ui/screen/overlay/translation/TranslationView.kt")
edit(trans,"import androidx.compose.ui.input.pointer.pointerInput",
           "import androidx.compose.ui.input.pointer.pointerInput\nimport androidx.compose.foundation.gestures.detectDragGestures")
edit(trans,"    private lateinit var targetHandleViewModel: TargetHandleViewModel",
"""    private lateinit var targetHandleViewModel: TargetHandleViewModel
    private var manualWindowX: Int? = null
    private var manualWindowY: Int? = null
    private fun moveFloatingWindow(context: Context, dx: Float, dy: Float) {
        val screen = ScreenInfoHolder.get()
        val maxX = (screen.width-layoutParams.width).coerceAtLeast(0)
        val maxY = (screen.height-layoutParams.height).coerceAtLeast(0)
        manualWindowX = ((manualWindowX ?: layoutParams.x) + dx.roundToInt()).coerceIn(0,maxX)
        manualWindowY = ((manualWindowY ?: layoutParams.y) + dy.roundToInt()).coerceIn(0,maxY)
        layoutParams.x = manualWindowX!!
        layoutParams.y = manualWindowY!!
        updateLayout(context)
    }""")
edit(trans,"""        super.cast(applicationContext)
        liveStateFlow.value = true""",
"""        if (manualWindowX != null && manualWindowY != null) {
            val s = ScreenInfoHolder.get()
            layoutParams.x = manualWindowX!!.coerceIn(0,(s.width-layoutParams.width).coerceAtLeast(0))
            layoutParams.y = manualWindowY!!.coerceIn(0,(s.height-layoutParams.height).coerceAtLeast(0))
        }
        super.cast(applicationContext)
        liveStateFlow.value = true""")
edit(trans,"""                            Spacer(modifier = Modifier.weight(1f)) // 로고 이미지와 IconButton 사이에 공간을 추가""",
"""                            Spacer(modifier = Modifier.weight(1f)) // logo and buttons spacing
                            Box(
                                modifier = Modifier
                                    .size(bottomMenuHeight)
                                    .pointerInput(Unit) {
                                        detectDragGestures(
                                            onDragStart = { onPauseDismissRunning() },
                                            onDragEnd = { onResumeDismissRunning() },
                                            onDragCancel = { onResumeDismissRunning() }
                                        ) { change, dragAmount ->
                                            change.consume()
                                            moveFloatingWindow(context,dragAmount.x,dragAmount.y)
                                        }
                                    },
                                contentAlignment = Alignment.Center
                            ) {
                                Text("⠿",fontSize = 19.sp,color = Color(0xFF747278))
                            }""")
print("overlay stability, small ball hit area, non-touch aiming overlay and movable translation frame patched")
