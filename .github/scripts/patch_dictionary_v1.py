#!/usr/bin/env python3
"""Offline dictionary import and floating translation word navigation."""
from pathlib import Path
root=Path(".")
base=Path("app/src/main/java/com/galaxy/airviewdictionary")
def edit(path,old,new):
 p=root/path; s=p.read_text("utf8"); n=s.count(old)
 if n!=1: raise RuntimeError(f"{path}: expected 1, got {n}: {old[:140]}")
 p.write_text(s.replace(old,new,1),"utf8"); print("edited",path)
dictdir=root/base/"data/local/dictionary"
dictdir.mkdir(parents=True,exist_ok=True)
(dictdir/"UserDictionary.kt").write_text(r'''package com.galaxy.airviewdictionary.data.local.dictionary

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.net.Uri
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.Locale

data class DictionaryEntry(val word: String, val definition: String, val source: String)

class UserDictionary(context: Context) : SQLiteOpenHelper(
    context.applicationContext, "user_dictionary_v1.db", null, 1
) {
    private val app = context.applicationContext

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("""CREATE TABLE entries (
            term TEXT PRIMARY KEY COLLATE NOCASE,
            word TEXT NOT NULL,
            definition TEXT NOT NULL,
            source TEXT NOT NULL
        )""")
        db.execSQL("""CREATE TABLE favorites (term TEXT PRIMARY KEY COLLATE NOCASE)""")
        db.execSQL("""CREATE TABLE history (term TEXT PRIMARY KEY COLLATE NOCASE, used_at INTEGER NOT NULL)""")
    }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

    fun find(word: String): DictionaryEntry? {
        val term = normalize(word)
        if (term.isBlank()) return null
        readableDatabase.rawQuery(
            "SELECT word,definition,source FROM entries WHERE term=? LIMIT 1", arrayOf(term)
        ).use { c ->
            if (c.moveToFirst()) return DictionaryEntry(c.getString(0),c.getString(1),c.getString(2))
        }
        return null
    }

    fun markHistory(word: String) {
        val term = normalize(word)
        if (term.isNotEmpty()) writableDatabase.execSQL(
            "INSERT OR REPLACE INTO history(term,used_at) VALUES(?,?)",
            arrayOf(term,System.currentTimeMillis())
        )
    }

    fun recentWords(): List<String> {
        val out=mutableListOf<String>()
        readableDatabase.rawQuery("SELECT term FROM history ORDER BY used_at DESC LIMIT 20", null).use { c ->
            while(c.moveToNext()) out.add(c.getString(0))
        }
        return out
    }

    fun toggleFavorite(word: String): Boolean {
        val term=normalize(word)
        if(term.isBlank()) return false
        val db=writableDatabase
        db.rawQuery("SELECT term FROM favorites WHERE term=?",arrayOf(term)).use { c ->
            if(c.moveToFirst()) {
                db.execSQL("DELETE FROM favorites WHERE term=?",arrayOf(term))
                return false
            }
        }
        db.execSQL("INSERT OR REPLACE INTO favorites(term) VALUES(?)",arrayOf(term))
        return true
    }

    fun favorite(word: String): Boolean {
        val term=normalize(word)
        readableDatabase.rawQuery("SELECT term FROM favorites WHERE term=?",arrayOf(term)).use { c ->
            return c.moveToFirst()
        }
    }

    /** UTF-8 plain text imports: tab-separated, CSV (quoted fields), or word=meaning. */
    fun importTextFile(uri: Uri, sourceName: String): Int {
        val ext=sourceName.substringAfterLast('.',"").lowercase(Locale.ROOT)
        require(ext in setOf("txt","tsv","csv")) {
            "仅支持 UTF-8 TXT、TSV、CSV。MDX/MDD 等二进制词典需独立解析器。"
        }
        val stream=app.contentResolver.openInputStream(uri) ?: error("Cannot open dictionary")
        val db=writableDatabase
        var inserted=0
        stream.use { input ->
            BufferedReader(InputStreamReader(input, Charsets.UTF_8)).use { reader ->
                db.beginTransaction()
                try {
                    val statement=db.compileStatement(
                        "INSERT OR REPLACE INTO entries(term,word,definition,source) VALUES(?,?,?,?)"
                    )
                    while (true) {
                        val raw=reader.readLine() ?: break
                        if (raw.length>32768) continue
                        val line=raw.trimStart('\uFEFF').trim()
                        if (line.isBlank() || line.startsWith("#")) continue
                        val (word,meaning)=splitLine(line,ext)
                        val term=normalize(word)
                        if(term.isBlank() || term.length>120 || meaning.isBlank()) continue
                        statement.clearBindings()
                        statement.bindString(1,term)
                        statement.bindString(2,word.trim())
                        statement.bindString(3,meaning.take(16000))
                        statement.bindString(4,sourceName)
                        statement.executeInsert()
                        inserted++
                        if (inserted>=300000) break
                    }
                    db.setTransactionSuccessful()
                } finally {
                    db.endTransaction()
                }
            }
        }
        return inserted
    }

    private fun splitLine(line: String, ext: String): Pair<String,String> {
        if('\t' in line) return line.substringBefore('\t') to line.substringAfter('\t')
        if(ext=="csv" || (',' in line && '=' !in line)) {
            val fields=csvFields(line)
            if(fields.size>=2) return fields.first() to fields.drop(1).joinToString(",")
        }
        if('=' in line) return line.substringBefore('=') to line.substringAfter('=')
        return "" to ""
    }

    /** CSV escaped quotes, commas inside quoted definitions. */
    internal fun csvFields(line: String): List<String> {
        val out=mutableListOf<String>();val buf=StringBuilder()
        var quoted=false;var i=0
        while(i<line.length) {
            when(val c=line[i]) {
                '"' -> {
                    if(quoted && i+1<line.length && line[i+1]=='"') {buf.append('"');i++}
                    else quoted=!quoted
                }
                ',' -> if(quoted) buf.append(c) else {out.add(buf.toString().trim());buf.setLength(0)}
                else -> buf.append(c)
            }
            i++
        }
        out.add(buf.toString().trim())
        return out
    }

    private fun normalize(word: String): String =
        word.trim().lowercase(Locale.ROOT).take(120)
}
''',"utf8")
actdir=root/base/"ui/screen/dictionary"
actdir.mkdir(parents=True,exist_ok=True)
(actdir/"DictionaryActivity.kt").write_text(r'''package com.galaxy.airviewdictionary.ui.screen.dictionary

import android.content.Context
import android.content.Intent
import android.speech.tts.TextToSpeech
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.lifecycleScope
import com.galaxy.airviewdictionary.data.local.dictionary.UserDictionary
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Locale

/** Searchable, offline, independent dictionary panel; never performs background OCR. */
class DictionaryActivity : ComponentActivity() {
    companion object {
        private const val EXTRA_WORD="dictionary_word"
        fun start(context: Context, word: String) {
            context.startActivity(Intent(context,DictionaryActivity::class.java)
                .putExtra(EXTRA_WORD,word.take(160))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }

    private lateinit var store: UserDictionary
    private var version by mutableIntStateOf(0)
    private var message by mutableStateOf("")
    private var tts: TextToSpeech?=null
    private var ttsReady=false

    private val chooseFile=registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if(uri!=null) {
            val name=contentResolver.query(uri,null,null,null,null)?.use { cursor ->
                val idx=cursor.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
                if(idx>=0 && cursor.moveToFirst()) cursor.getString(idx) else null
            } ?: "dictionary.tsv"
            message="正在导入…"
            lifecycleScope.launch {
                val outcome=withContext(Dispatchers.IO) {
                    runCatching { store.importTextFile(uri,name) }
                }
                outcome.onSuccess { count ->
                    version++
                    message="已导入 $count 条词条"
                }.onFailure { error ->
                    message="导入失败：${error.message}"
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store=UserDictionary(this)
        tts=TextToSpeech(this) { status ->
            ttsReady=status==TextToSpeech.SUCCESS
            if(ttsReady) tts?.language=Locale.US
        }
        val initial=intent.getStringExtra(EXTRA_WORD).orEmpty()
        window?.setLayout((resources.displayMetrics.widthPixels*.91f).toInt(),-2)
        setContent {
            MaterialTheme(colorScheme=lightColorScheme(primary=Color(0xFF315F9D))) {
                DictionaryScreen(initial)
            }
        }
    }

    @Composable
    private fun DictionaryScreen(initial: String) {
        var input by remember { mutableStateOf(initial) }
        var query by remember { mutableStateOf(initial) }
        var favorited by remember { mutableStateOf(false) }
        var result by remember { mutableStateOf<com.galaxy.airviewdictionary.data.local.dictionary.DictionaryEntry?>(null) }
        var history by remember { mutableStateOf(emptyList<String>()) }

        LaunchedEffect(query, version) {
            val found=withContext(Dispatchers.IO) {
                store.markHistory(query)
                store.find(query)
            }
            result=found
            favorited=withContext(Dispatchers.IO) { store.favorite(query) }
            history=withContext(Dispatchers.IO) { store.recentWords() }
        }
        Surface(modifier=Modifier.fillMaxWidth(),color=Color.White) {
            Column(Modifier.padding(16.dp).heightIn(max=560.dp)) {
                Row(verticalAlignment=Alignment.CenterVertically) {
                    TextButton(onClick={finish()}) { Text("← 返回") }
                    Spacer(Modifier.weight(1f))
                    Text("本地词典", fontWeight=FontWeight.Bold, fontSize=18.sp)
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick={
                        chooseFile.launch(arrayOf("text/*","application/octet-stream","*/*"))
                    }) { Text("导入") }
                }
                Row(verticalAlignment=Alignment.CenterVertically) {
                    OutlinedTextField(
                        value=input,onValueChange={input=it.take(160)},
                        singleLine=true,label={Text("查询单词")},
                        modifier=Modifier.weight(1f)
                    )
                    Spacer(Modifier.width(8.dp))
                    Button(onClick={query=input.trim()}) { Text("查找") }
                }
                Spacer(Modifier.height(10.dp))
                if(message.isNotEmpty()) Text(message,fontSize=12.sp,color=Color(0xFF3267A0))
                Column(Modifier.fillMaxWidth().weight(1f,fill=false).verticalScroll(rememberScrollState())) {
                    if(query.isNotBlank()) {
                        Row(verticalAlignment=Alignment.CenterVertically) {
                            Text(query,fontSize=26.sp,fontWeight=FontWeight.Bold,modifier=Modifier.weight(1f))
                            TextButton(onClick={
                                if(ttsReady) tts?.speak(query,TextToSpeech.QUEUE_FLUSH,null,"dictionary_word")
                                else Toast.makeText(this@DictionaryActivity,"语音引擎尚未就绪",Toast.LENGTH_SHORT).show()
                            }) { Text("🔊") }
                            TextButton(onClick={
                                lifecycleScope.launch {
                                    favorited=withContext(Dispatchers.IO){store.toggleFavorite(query)}
                                }
                            }) { Text(if(favorited) "★" else "☆") }
                        }
                        HorizontalDivider()
                        Spacer(Modifier.height(10.dp))
                        if(result!=null) {
                            Text("释义 · ${result!!.source}",fontSize=12.sp,color=Color.Gray)
                            Spacer(Modifier.height(7.dp))
                            Text(result!!.definition,fontSize=16.sp,lineHeight=24.sp)
                        } else {
                            Text("未在已导入词典中找到该词。",color=Color.Gray)
                            Text("支持 UTF-8 TSV / CSV / TXT。示例：",fontSize=12.sp)
                            Text("book\\t书；书籍",fontSize=13.sp,color=Color(0xFF315F9D))
                        }
                    }
                    if(history.isNotEmpty()) {
                        Spacer(Modifier.height(15.dp))
                        Text("最近查询",fontWeight=FontWeight.Bold,fontSize=14.sp)
                        history.filter{it!=query}.take(10).forEach { term ->
                            Text(term,Modifier.fillMaxWidth().clickable {
                                input=term;query=term
                            }.padding(vertical=7.dp),fontSize=14.sp,color=Color(0xFF315F9D))
                        }
                    }
                }
                Spacer(Modifier.height(7.dp))
                Text("离线词库由用户导入；不包含第三方词典的版权数据。",fontSize=11.sp,color=Color.Gray)
            }
        }
    }

    override fun onDestroy() {
        tts?.stop();tts?.shutdown();store.close()
        super.onDestroy()
    }
}
''',"utf8")
edit("app/src/main/AndroidManifest.xml",
     '        <activity\n            android:name=".ui.screen.main.SettingsActivity"',
     '''        <activity
            android:name=".ui.screen.dictionary.DictionaryActivity"
            android:exported="false"
            android:windowSoftInputMode="adjustResize"
            android:theme="@android:style/Theme.Material.Light.Dialog.NoActionBar" />

        <activity
            android:name=".ui.screen.main.SettingsActivity"''')
trans=str(base/"ui/screen/overlay/translation/TranslationView.kt")
edit(trans,"import androidx.compose.ui.text.buildAnnotatedString",
'''import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.LinkInteractionListener
import androidx.compose.ui.text.withLink
import com.galaxy.airviewdictionary.ui.screen.dictionary.DictionaryActivity''')
# Only source span changes; leave result/translation/UI untouched.
edit(trans,"""                    append(sourceText)
                }
            }
            withStyle(ParagraphStyle(textDirection = resultDirection))""",
"""                    val tokenRegex = Regex("[A-Za-z]+(?:['’-][A-Za-z]+)*")
                    var cursor = 0
                    tokenRegex.findAll(sourceText).forEach { match ->
                        append(sourceText.substring(cursor,match.range.first))
                        val token=match.value
                        withLink(LinkAnnotation.Clickable(
                            tag="dict:$token",
                            linkInteractionListener=LinkInteractionListener {
                                onPauseDismissRunning()
                                DictionaryActivity.start(context,token)
                            }
                        )) { append(token) }
                        cursor=match.range.last+1
                    }
                    append(sourceText.substring(cursor))
                }
            }
            withStyle(ParagraphStyle(textDirection = resultDirection))""")
# Also expose dictionary import in settings without affecting original controls
settings=str(base/"ui/screen/main/SettingsActivity.kt")
edit(settings,
     'import com.galaxy.airviewdictionary.ui.screen.reply.ReplyActivity',
     'import com.galaxy.airviewdictionary.ui.screen.reply.ReplyActivity') if False else None
# Insert via a reliable existing unique import
edit(settings,
     'import com.galaxy.airviewdictionary.ui.screen.overlay.targethandle.TargetHandleView',
     'import com.galaxy.airviewdictionary.ui.screen.overlay.targethandle.TargetHandleView\nimport com.galaxy.airviewdictionary.ui.screen.dictionary.DictionaryActivity')
edit(settings,
     '''                            MenuCategory(
                                painter = painterResource(id = R.drawable.ic_menubar),''',
     '''                            MenuItem(
                                menuItemPosition = MenuItemPosition.Bottom,
                                onClick = { DictionaryActivity.start(context, "") }
                            ) {
                                Row(
                                    modifier = Modifier.fillMaxWidth().padding(horizontal=16.dp,vertical=12.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text("📖 自定义本地词典 / 导入词库", color = contentColor)
                                }
                            }

                            MenuCategory(
                                painter = painterResource(id = R.drawable.ic_menubar),''')
print("offline dictionary, import activity, word click navigation and back integrated")
