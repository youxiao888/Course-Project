#!/usr/bin/env python3
"""V2: in-window lookup, draggable compact panel, single-tap floating controls."""
from pathlib import Path
base=Path("app/src/main/java/com/galaxy/airviewdictionary")
def change(path,old,new):
 p=Path(path); s=p.read_text("utf8"); k=s.count(old)
 if k!=1: raise RuntimeError(f"{path}: expected one anchor, found {k}: {old[:110]!r}")
 p.write_text(s.replace(old,new,1),"utf8")
 print("patched",p)
def create(rel,body):
 p=base/rel; p.parent.mkdir(parents=True,exist_ok=True);p.write_text(body,"utf8");print("created",p)

create("ui/screen/overlay/targethandle/FloatingControlMenu.kt",r'''package com.galaxy.airviewdictionary.ui.screen.overlay.targethandle

import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.PopupWindow
import android.widget.TextView
import android.widget.EditText
import com.galaxy.airviewdictionary.data.local.dictionary.UserDictionary
import com.galaxy.airviewdictionary.data.local.vision.TextDetectMode
import com.galaxy.airviewdictionary.data.local.preference.PreferenceRepository
import com.galaxy.airviewdictionary.ui.screen.overlay.translation.TranslationView
import kotlin.concurrent.thread

/** Compact iOS-inspired control panel anchored to floating bubble.
 *  Never starts SettingsActivity or another app on tap.
 */
internal class FloatingControlMenu(
    private val context: Context,
    private val anchor: View,
    private val setMode: (TextDetectMode)->Unit,
    private val toggleDock: ()->Boolean,
    private val isDockDisabled: ()->Boolean,
) {
    private fun dp(v:Int)=(v*context.resources.displayMetrics.density).toInt()
    private val black=Color.rgb(25,28,34)
    private val muted=Color.rgb(107,114,128)
    private val blue=Color.rgb(0,122,255)
    private fun shape(c:Int,r:Int)=GradientDrawable().apply {
        setColor(c);cornerRadius=dp(r).toFloat()
    }
    private var popup: PopupWindow?=null
    fun toggle() {
        if(popup?.isShowing==true) {popup?.dismiss();return}
        val root=LinearLayout(context).apply {
            orientation=LinearLayout.VERTICAL
            background=shape(Color.WHITE,23)
            elevation=dp(12).toFloat()
            setPadding(dp(17),dp(13),dp(17),dp(12))
        }
        fun header(text:String,size:Float,color:Int=black):TextView =
            TextView(context).apply {
                this.text=text;setTextColor(color);textSize=size
                typeface=Typeface.create("sans-serif",Typeface.NORMAL)
                setPadding(dp(4),dp(4),dp(4),dp(9))
            }
        root.addView(header("屏幕取词",19f).also{it.setTypeface(null,Typeface.BOLD)})
        root.addView(header("拖动选择文字 · 点击切换模式",12f,muted))
        fun row(label:String,icon:String,onClick:()->Unit) {
            val cell=TextView(context).apply {
                text="$icon    $label"
                textSize=15f
                setTextColor(black)
                gravity=Gravity.CENTER_VERTICAL
                setPadding(dp(13),0,dp(11),0)
                background=shape(Color.rgb(247,248,250),12)
                setOnClickListener{ onClick() }
            }
            root.addView(cell,LinearLayout.LayoutParams(-1,dp(43)).apply {bottomMargin=dp(7)})
        }
        row("拖动查单词","Aa") {setMode(TextDetectMode.WORD);popup?.dismiss()}
        row("拖动查句子","≡") {setMode(TextDetectMode.SENTENCE);popup?.dismiss()}
        row("拖动查段落","¶") {setMode(TextDetectMode.PARAGRAPH);popup?.dismiss()}
        row("全屏框选翻译","⛶") {setMode(TextDetectMode.SELECT);popup?.dismiss()}
        row(if(isDockDisabled())"允许自动贴边" else "禁止自动贴边","⊞") {
            toggleDock();popup?.dismiss()
        }
        val wordBox=EditText(context).apply {
            setSingleLine(true);hint="输入单词，在此查看释义"
            textSize=14f;setTextColor(black)
            setPadding(dp(10),0,dp(10),0)
            background=shape(Color.rgb(245,246,249),10)
        }
        root.addView(wordBox,LinearLayout.LayoutParams(-1,dp(43)).apply{bottomMargin=dp(5)})
        val meaning=header("可导入的词典：MDX / TXT / TSV / CSV",12f,muted)
        meaning.setPadding(dp(4),dp(6),dp(4),dp(5))
        root.addView(meaning)
        row("查询","⌕") {
            val word=wordBox.text.toString().trim()
            if(word.isNotBlank()) {
                meaning.text="正在检索…"
                thread(name="dictionary-popup-search") {
                    val detail=runCatching {
                        val store=UserDictionary(context)
                        try {store.find(word)} finally {store.close()}
                    }.getOrNull()
                    root.post {
                        meaning.text=detail?.definition?.take(450) ?: "本地词典未找到：$word"
                    }
                }
            }
        }
        row("关闭菜单","×") {popup?.dismiss()}
        val pw=PopupWindow(root,dp(302),WindowManager.LayoutParams.WRAP_CONTENT,true).apply {
            isOutsideTouchable=true
            elevation=dp(12).toFloat()
            setBackgroundDrawable(android.graphics.drawable.ColorDrawable(Color.TRANSPARENT))
            inputMethodMode=PopupWindow.INPUT_METHOD_NEEDED
            softInputMode=WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE
        }
        popup=pw
        val loc=IntArray(2);anchor.getLocationOnScreen(loc)
        val dm=context.resources.displayMetrics
        val maxX=(dm.widthPixels-dp(310)).coerceAtLeast(4)
        val x=(loc[0]-dp(15)).coerceIn(dp(4),maxX)
        val y=if(loc[1]>dm.heightPixels/2) dp(24) else (loc[1]+dp(70)).coerceAtMost(dm.heightPixels/2)
        pw.showAtLocation(anchor,Gravity.TOP or Gravity.START,x,y)
    }
    fun dismiss(){popup?.dismiss();popup=null}
}
''')

handle=str(base/"ui/screen/overlay/targethandle/TargetHandleView.kt")
change(handle,
'''    private var viewHeight = 0''',
'''    private var floatingControls: FloatingControlMenu? = null
    private fun toggleFloatingControls(context: Context) {
        val anchor=view ?: return
        if(floatingControls==null) {
            floatingControls=FloatingControlMenu(
                context,anchor,
                setMode={ viewModel.updateTextDetectMode(it) },
                toggleDock={
                    val next=!noEdgeDockingEnabled
                    viewModel.preferenceRepository.update(PreferenceRepository.NO_EDGE_DOCKING,next)
                    noEdgeDockingEnabled=next
                    next
                },
                isDockDisabled={noEdgeDockingEnabled}
            )
        }
        floatingControls?.toggle()
    }

    private var viewHeight = 0''')
# PreferenceRepository may not imported in Handle, use fully qualified to compile.
change(handle,"PreferenceRepository.NO_EDGE_DOCKING,next","com.galaxy.airviewdictionary.data.local.preference.PreferenceRepository.NO_EDGE_DOCKING,next")
change(handle,
'''                override fun onSingleTapConfirmed(e: MotionEvent): Boolean {
                    return true
                }''',
'''                override fun onSingleTapConfirmed(e: MotionEvent): Boolean {
                    toggleFloatingControls(applicationContext)
                    return true
                }''')
old='''                override fun onDoubleTap(e: MotionEvent): Boolean {
                    if (!SettingsActivity.liveStateFlow.value) {
                        launchInAVDCoroutineScope {
                            delay(200)
                            if (!VisionTextView.INSTANCE.isRunning.get()) {
                                applicationContext.vibrate()
                                SettingsActivity.start(applicationContext)
                            }
                        }
                    }
                    return true
                }'''
change(handle,old,'''                override fun onDoubleTap(e: MotionEvent): Boolean {
                    toggleFloatingControls(applicationContext)
                    return true
                }''')
change(handle,
'''    override fun clear() {
        dragHandleDockingJob?.cancel()''',
'''    override fun clear() {
        floatingControls?.dismiss()
        floatingControls=null
        dragHandleDockingJob?.cancel()''')

trans=str(base/"ui/screen/overlay/translation/TranslationView.kt")
# Remove old parent gesture detector capturing drag touches, not the new header drag.
change(trans,
'''                        .pointerInput(Unit) {
                            detectTapGestures(
                                onPress = {
                                    // 터치가 시작되면 dismiss running pause
                                    onPauseDismissRunning()
                                    tryAwaitRelease()
                                    // 터치가 끝난 후 dismiss running resume
                                    onResumeDismissRunning()
                                }
                            )
                        }''',
'''                        // Interaction is delegated to actual controls. Do not intercept
                        // all pointer events in the parent: that breaks dragging.''')
# The old code has a spurious trailing comment? replace just uses valid modifier chain after .alpha with comment, okay.
change(trans,
'''import androidx.compose.ui.text.buildAnnotatedString''',
'''import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.weight
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Button
import androidx.compose.material3.TextButton
import androidx.compose.material3.Surface
import androidx.compose.material3.HorizontalDivider
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.text.font.FontWeight
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import com.galaxy.airviewdictionary.data.local.dictionary.UserDictionary
import com.galaxy.airviewdictionary.data.local.dictionary.DictionaryEntry
import android.text.Html''')
# duplicates LAUNCHEDEFFECT etc imports are compile errors "conflicting import"? Kotlin duplicate import tolerated? remove duplicates.
p=Path(trans); source=p.read_text("utf8")
for imp in ["import androidx.compose.runtime.LaunchedEffect","import androidx.compose.ui.text.font.FontWeight","import androidx.compose.foundation.layout.weight"]:
 # weight is an extension internal? Modifier.weight from RowScope/ColumnScope, import may error (internal). do not import
 if imp.endswith(".weight"): source=source.replace(imp+"\n","")
 elif source.count(imp+"\n")>1: source=source.replace(imp+"\n","",source.count(imp+"\n")-1)
p.write_text(source,"utf8")

change(trans,
'''    private lateinit var targetHandleViewModel: TargetHandleViewModel''',
'''    private lateinit var targetHandleViewModel: TargetHandleViewModel
    private var dictionaryWord by mutableStateOf<String?>(null)
    private val dictionaryBackStack = mutableStateListOf<String>()
    private var holdTranslation by mutableStateOf(false)
    private var lastDisplay: Pair<VisionText, Transaction>? = null
    private var savedNormalHeight: Int?=null
    private var savedNormalWidth: Int?=null

    private fun enterDictionary(context: Context, word: String) {
        val value=word.trim().take(120)
        if(value.isEmpty()) return
        if(dictionaryWord!=null) dictionaryBackStack.add(dictionaryWord!!)
        if(dictionaryWord==null) {
            savedNormalHeight=layoutParams.height
            savedNormalWidth=layoutParams.width
        }
        holdTranslation=true
        targetHandleViewModel.pauseDismissRunning()
        dictionaryWord=value
        val screen=ScreenInfoHolder.get()
        val density=context.resources.displayMetrics.density
        layoutParams.width=minOf(screen.width-(24*density).toInt(),maxOf(layoutParams.width,(355*density).toInt()))
        layoutParams.height=minOf(screen.height-(70*density).toInt(),maxOf(layoutParams.height,(435*density).toInt()))
        layoutParams.x=layoutParams.x.coerceIn(0,(screen.width-layoutParams.width).coerceAtLeast(0))
        layoutParams.y=layoutParams.y.coerceIn(0,(screen.height-layoutParams.height).coerceAtLeast(0))
        manualWindowX=layoutParams.x
        manualWindowY=layoutParams.y
        updateLayout(context)
    }

    private fun dictionaryBack(context: Context) {
        if(dictionaryBackStack.isNotEmpty()) {
            dictionaryWord=dictionaryBackStack.removeAt(dictionaryBackStack.size-1)
        } else {
            dictionaryWord=null
            savedNormalWidth?.let{layoutParams.width=it}
            savedNormalHeight?.let{layoutParams.height=it}
            updateLayout(context)
        }
    }''')
# Compose root replace only exact section preserving old logic fallback
start='''        translationState?.let { (visionText, translation) ->
            if (visionText != null && translation != null) {
                if (isAttachedToWindow()) {
                    val fontSizeSp = getRenderFontSizeSp(context, visionText.fontHeight).sp
                    TranslationBox(
                        translation,
                        fontSizeSp,
                        onPauseDismissRunning = { targetHandleViewModel.pauseDismissRunning() },
                        onResumeDismissRunning = { targetHandleViewModel.resumeDismissRunning() },
                        onRerunDismissRunning = { targetHandleViewModel.rerunDismissRunning() }
                    )
                }
            }
        } ?: clear()'''
new='''        val current=translationState?.let { (v,t) -> if(v!=null && t!=null) Pair(v,t) else null }
        if(current!=null) lastDisplay=current
        val display=current ?: if(holdTranslation) lastDisplay else null
        if(dictionaryWord!=null) {
            InWindowDictionary(
                context=context,
                word=dictionaryWord!!,
                onBack={dictionaryBack(context)},
                onNavigate={enterDictionary(context,it)}
            )
        } else if(display!=null && isAttachedToWindow()) {
            val (visionText,translation)=display
            val fontSizeSp=getRenderFontSizeSp(context,visionText.fontHeight).sp
            TranslationBox(
                translation,fontSizeSp,
                onPauseDismissRunning={targetHandleViewModel.pauseDismissRunning()},
                onResumeDismissRunning={targetHandleViewModel.resumeDismissRunning()},
                onRerunDismissRunning={targetHandleViewModel.rerunDismissRunning()}
            )
        } else if(!holdTranslation) {
            clear()
        }'''
change(trans,start,new)
change(trans,
'''        super.cast(applicationContext)
        liveStateFlow.value = true''',
'''        lastDisplay=Pair(visionText,translation)
        super.cast(applicationContext)
        liveStateFlow.value = true''')
change(trans,
'''        drawnTranslation = null
        super.clear()''',
'''        drawnTranslation = null
        dictionaryWord=null
        dictionaryBackStack.clear()
        holdTranslation=false
        lastDisplay=null
        savedNormalHeight=null
        savedNormalWidth=null
        manualWindowX=null
        manualWindowY=null
        super.clear()''')
# Existing source links from previous patch. Replace launch external activity with inline page.
change(trans,'DictionaryActivity.start(context,token)','enterDictionary(context,token)')
# Panel layout: use existing size but replace bottom drag handle with bigger and place header at the top
change(trans,
'''                                    .size(bottomMenuHeight)
                                    .pointerInput(Unit) {
                                        detectDragGestures(''',
'''                                    .size(bottomMenuHeight)
                                    .pointerInput(Unit) {
                                        detectDragGestures(''')
# actual foot drag fixed by deleting outer parent pointerInput; ensure top row contains easy drag affordance
# Add in-window dictionary panel as member before class closing.
p=Path(trans); s=p.read_text("utf8")
insert=r'''
    @Composable
    private fun InWindowDictionary(
        context: Context,
        word: String,
        onBack: ()->Unit,
        onNavigate: (String)->Unit
    ) {
        var entry by remember(word) { mutableStateOf<DictionaryEntry?>(null) }
        var loading by remember(word) { mutableStateOf(true) }
        var input by remember(word) { mutableStateOf(word) }
        var error by remember(word) { mutableStateOf<String?>(null) }
        LaunchedEffect(word) {
            loading=true
            val found=withContext(Dispatchers.IO) {
                runCatching {
                    val dict=UserDictionary(context)
                    try {dict.markHistory(word);dict.find(word)} finally {dict.close()}
                }
            }
            entry=found.getOrNull()
            error=found.exceptionOrNull()?.message
            loading=false
        }
        val bg=Color(0xFFFDFDFE)
        val ink=Color(0xFF1C1C1E)
        val primary=Color(0xFF007AFF)
        Surface(
            modifier=Modifier.fillMaxSize().padding(3.dp),
            color=bg,shadowElevation=9.dp,shape=RoundedCornerShape(22.dp)
        ) {
            Column(Modifier.fillMaxSize()) {
                Row(
                    modifier=Modifier.fillMaxWidth().height(51.dp)
                        .background(Color(0xFFF6F7FA))
                        .pointerInput(Unit) {
                            detectDragGestures(
                                onDragStart={ targetHandleViewModel.pauseDismissRunning() },
                                onDragEnd={ },
                                onDragCancel={ }
                            ) { change,amount ->
                                change.consume();moveFloatingWindow(context,amount.x,amount.y)
                            }
                        }
                        .padding(horizontal=13.dp),
                    verticalAlignment=Alignment.CenterVertically
                ) {
                    TextButton(onClick=onBack) { Text("‹ 返回",color=primary,fontSize=15.sp) }
                    Spacer(Modifier.weight(1f))
                    Text("词典",color=ink,fontWeight=FontWeight.SemiBold,fontSize=16.sp)
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick={dictionaryWord=null; holdTranslation=false; clear()}) {
                        Text("×",fontSize=24.sp,color=Color(0xFF8E8E93))
                    }
                }
                HorizontalDivider(color=Color(0xFFEDEEF2))
                Row(Modifier.fillMaxWidth().padding(horizontal=15.dp,vertical=8.dp),verticalAlignment=Alignment.CenterVertically) {
                    OutlinedTextField(
                        value=input,onValueChange={input=it.take(120)},
                        modifier=Modifier.weight(1f),singleLine=true,
                        placeholder={Text("查找单词")},
                        shape=RoundedCornerShape(13.dp)
                    )
                    TextButton(onClick={onNavigate(input)}) {Text("查询",color=primary)}
                }
                Column(
                    modifier=Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState())
                        .padding(horizontal=19.dp,vertical=8.dp)
                ) {
                    Text(word,fontSize=29.sp,fontWeight=FontWeight.Bold,color=ink)
                    Spacer(Modifier.height(7.dp))
                    Text(entry?.source ?: "离线词典",fontSize=12.sp,color=Color(0xFF8E8E93))
                    Spacer(Modifier.height(9.dp))
                    HorizontalDivider(color=Color(0xFFEEEEF0))
                    Spacer(Modifier.height(12.dp))
                    when {
                        loading -> Text("正在检索本地词库…",color=Color.Gray)
                        error!=null -> Text("读取失败：$error",color=Color(0xFFC54444))
                        entry==null -> {
                            Text("未找到该词",fontSize=16.sp,color=ink)
                            Spacer(Modifier.height(9.dp))
                            Text("请在设置中导入你拥有使用权的牛津词典 MDX 或其他支持的词库文件。",fontSize=13.sp,color=Color.Gray)
                        }
                        else -> {
                            val definition=entry!!.definition
                            if(definition.trimStart().startsWith("<")) {
                                // Preserve Oxford MDX entry HTML layout without
                                // allowing scripts, file access, or network requests.
                                androidx.compose.ui.viewinterop.AndroidView(
                                    factory={ctx->
                                        android.webkit.WebView(ctx).apply {
                                            setBackgroundColor(android.graphics.Color.TRANSPARENT)
                                            settings.javaScriptEnabled=false
                                            settings.allowFileAccess=false
                                            settings.allowContentAccess=false
                                            settings.blockNetworkLoads=true
                                            isVerticalScrollBarEnabled=false
                                            webViewClient=object:android.webkit.WebViewClient() {
                                                override fun shouldInterceptRequest(
                                                    view:android.webkit.WebView?,
                                                    request:android.webkit.WebResourceRequest?
                                                ):android.webkit.WebResourceResponse? {
                                                    val uri=request?.url ?: return null
                                                    if(uri.host!="dictionary.invalid") return android.webkit.WebResourceResponse(
                                                        "text/plain","utf-8",java.io.ByteArrayInputStream(byteArrayOf()))
                                                    val bytes=com.galaxy.airviewdictionary.data.local.dictionary.MdxCatalog.asset(
                                                        ctx,entry?.source.orEmpty(),uri.encodedPath.orEmpty()
                                                    ) ?: return null
                                                    val path=uri.path.orEmpty().lowercase()
                                                    val mime=when {
                                                        path.endsWith(".css")->"text/css"
                                                        path.endsWith(".png")->"image/png"
                                                        path.endsWith(".jpg")||path.endsWith(".jpeg")->"image/jpeg"
                                                        path.endsWith(".gif")->"image/gif"
                                                        path.endsWith(".svg")->"image/svg+xml"
                                                        path.endsWith(".mp3")->"audio/mpeg"
                                                        path.endsWith(".wav")->"audio/wav"
                                                        else->"application/octet-stream"
                                                    }
                                                    return android.webkit.WebResourceResponse(
                                                        mime,if(mime.startsWith("text/"))"utf-8" else null,
                                                        java.io.ByteArrayInputStream(bytes)
                                                    )
                                                }
                                                override fun shouldOverrideUrlLoading(
                                                    view:android.webkit.WebView?,
                                                    request:android.webkit.WebResourceRequest?
                                                ):Boolean {
                                                    val url=request?.url ?: return true
                                                    val key=when(url.scheme) {
                                                        "bword","entry" -> url.schemeSpecificPart
                                                        else -> null
                                                    }
                                                    if(!key.isNullOrBlank())onNavigate(key.removePrefix("//"))
                                                    return true
                                                }
                                            }
                                        }
                                    },
                                    update={view->
                                        if(view.tag != definition) {
                                            view.tag=definition
                                            val html="""<html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{font-family:-apple-system,Roboto,sans-serif;font-size:15px;line-height:1.58;color:#1C1C1E;margin:0;padding:3px}img{max-width:100%;height:auto}table{max-width:100%}</style></head><body>""" + definition + "</body></html>"
                                            view.loadDataWithBaseURL("https://dictionary.invalid/",html,"text/html","utf-8",null)
                                        }
                                    },
                                    modifier=Modifier.fillMaxWidth().height(315.dp)
                                )
                            } else Text(definition,fontSize=15.sp,lineHeight=24.sp,color=ink)
                        }
                    }
                }
                HorizontalDivider(color=Color(0xFFEDEEF2))
                Row(
                    modifier=Modifier.fillMaxWidth().height(46.dp).padding(horizontal=18.dp),
                    verticalAlignment=Alignment.CenterVertically
                ) {
                    Text("本地 · 不跳转应用",fontSize=11.sp,color=Color(0xFF8E8E93))
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick=onBack) {Text("返回原文",color=primary,fontSize=13.sp)}
                }
            }
        }
    }
'''
marker="\n}\n"
idx=s.rfind(marker)
if idx<0:raise RuntimeError("last class brace missing")
p.write_text(s[:idx]+insert+s[idx:],"utf8")
print("patched same-overlay dictionary and touch-safe draggable panel")
