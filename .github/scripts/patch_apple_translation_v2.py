#!/usr/bin/env python3
from pathlib import Path
p=Path("app/src/main/java/com/galaxy/airviewdictionary/ui/screen/overlay/translation/TranslationView.kt")
s=p.read_text("utf8")
a='    @Composable\n    fun TranslationBox('
b='    @Composable\n    private fun InWindowDictionary('
if s.count(a)!=1 or s.count(b)!=1:raise RuntimeError("TranslationBox anchor mismatch")
start=s.index(a);end=s.index(b,start)
body=r'''    @Composable
    fun TranslationBox(
        translation: Transaction,
        fontSize: TextUnit = 18.sp,
        enableAutoResize: Boolean = true,
        onPauseDismissRunning: () -> Unit,
        onResumeDismissRunning: () -> Unit,
        onRerunDismissRunning: () -> Unit,
    ) {
        drawnTranslation=translation
        val context=LocalContext.current
        val source=translation.sourceText.orEmpty()
        val result=translation.resultText.orEmpty()
        val ink=Color(0xFF1C1C1E)
        val blue=Color(0xFF007AFF)
        val secondary=Color(0xFF8E8E93)
        val separator=Color(0xFFE8E8ED)
        val styledSource=buildAnnotatedString {
            val re=Regex("[A-Za-z]+(?:['’-][A-Za-z]+)*")
            var from=0
            for(match in re.findAll(source)) {
                append(source.substring(from,match.range.first))
                val word=match.value
                withLink(LinkAnnotation.Clickable(
                    tag="dict:$word",
                    linkInteractionListener=LinkInteractionListener {
                        enterDictionary(context,word)
                    }
                )) {
                    withStyle(SpanStyle(color=blue)){append(word)}
                }
                from=match.range.last+1
            }
            append(source.substring(from))
        }
        Surface(
            modifier=Modifier.fillMaxSize().padding(3.dp),
            color=Color(0xFFFDFDFE),
            shape=RoundedCornerShape(22.dp),
            shadowElevation=10.dp
        ) {
            Column(Modifier.fillMaxSize()) {
                Row(
                    modifier=Modifier.fillMaxWidth().height(54.dp)
                        .background(Color(0xFFF4F5F8))
                        .pointerInput(Unit) {
                            detectDragGestures(
                                onDragStart={onPauseDismissRunning()},
                                onDragEnd={},
                                onDragCancel={}
                            ) { event,delta->
                                event.consume()
                                moveFloatingWindow(context,delta.x,delta.y)
                            }
                        }.padding(horizontal=13.dp),
                    verticalAlignment=Alignment.CenterVertically
                ) {
                    Text("⠿",fontSize=20.sp,color=secondary)
                    Spacer(Modifier.width(9.dp))
                    Column(Modifier.weight(1f)) {
                        Text("屏幕翻译",fontWeight=FontWeight.SemiBold,fontSize=14.sp,color=ink)
                        Text("点击蓝色单词查看释义",fontSize=10.sp,color=secondary)
                    }
                    TextButton(onClick={targetHandleViewModel.playTTS(translation)}) {
                        Text("🔊",fontSize=17.sp,color=ink)
                    }
                    TextButton(onClick={
                        Regex("[A-Za-z]+").find(source)?.value?.let{enterDictionary(context,it)}
                    }) {
                        Text("⌕",fontSize=22.sp,color=ink)
                    }
                    TextButton(onClick={onResumeDismissRunning();clear()}) {
                        Text("×",fontSize=24.sp,color=secondary)
                    }
                }
                HorizontalDivider(color=separator)
                Column(
                    Modifier.fillMaxWidth().weight(1f)
                        .verticalScroll(rememberScrollState())
                        .padding(horizontal=18.dp,vertical=12.dp)
                ) {
                    Text("原文",fontSize=11.sp,color=secondary)
                    Spacer(Modifier.height(5.dp))
                    Text(styledSource,fontSize=fontSize,
                        lineHeight=(fontSize.value*1.45f).sp,color=ink)
                    Spacer(Modifier.height(13.dp))
                    HorizontalDivider(color=separator)
                    Spacer(Modifier.height(12.dp))
                    Text("翻译",fontSize=11.sp,color=secondary)
                    Spacer(Modifier.height(5.dp))
                    Text(result,fontSize=fontSize,
                        lineHeight=(fontSize.value*1.5f).sp,
                        color=Color(0xFF45464B))
                }
                HorizontalDivider(color=separator)
                Row(
                    modifier=Modifier.fillMaxWidth().height(44.dp)
                        .padding(horizontal=13.dp),
                    verticalAlignment=Alignment.CenterVertically
                ) {
                    TextButton(onClick={
                        Regex("[A-Za-z]+").find(source)?.value?.let{enterDictionary(context,it)}
                    }){Text("词典",fontSize=13.sp,color=blue)}
                    Spacer(Modifier.weight(1f))
                    Text("拖动顶部移动",fontSize=10.sp,color=secondary)
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick={
                        val cb=context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                        cb.setPrimaryClip(ClipData.newPlainText("Translation",source+"\n"+result))
                        onRerunDismissRunning()
                    }) {Text("复制",fontSize=13.sp,color=blue)}
                }
            }
        }
    }

'''
s=s[:start]+body+s[end:]
old='''            viewWidth,
            viewHeight,
            layoutPosX,
            layoutPosY,'''
new='''            viewWidth,
            maxOf(viewHeight, (230 * applicationContext.resources.displayMetrics.density).toInt())
                .coerceAtMost(viewMaxHeight),
            layoutPosX,
            layoutPosY.coerceIn(0, screenInfo.height -
                maxOf(viewHeight, (230 * applicationContext.resources.displayMetrics.density).toInt())
                    .coerceAtMost(viewMaxHeight)),'''
if s.count(old)!=1:raise RuntimeError("Layout window fragment missing")
s=s.replace(old,new,1)
p.write_text(s,"utf8")
print("iOS-style translation panel with draggable top bar and inline lexical links patched")
