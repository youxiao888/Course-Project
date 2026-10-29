#!/usr/bin/env python3
"""MDX reader integration. Uses GPL-3.0 mdict4j; preserve license notice."""
from pathlib import Path
b=Path("app/src/main/java/com/galaxy/airviewdictionary/data/local/dictionary")
def edit(p,old,new):
 p=Path(p);s=p.read_text("utf8")
 if s.count(old)!=1:raise RuntimeError(f"{p} anchor {s.count(old)}")
 p.write_text(s.replace(old,new,1),"utf8")
p=Path("app/build.gradle.kts");s=p.read_text("utf8")
s=s.replace("dependencies {",'dependencies {\n    implementation("tokyo.northside:mdict4j:0.4.0") {\n        exclude(group = "com.google.code.findbugs", module = "annotations")\n    }',1)
p.write_text(s,"utf8")
edit(b/"UserDictionary.kt",'        return null\n    }\n\n    fun markHistory',
     '        return MdxCatalog.lookup(app,word)\n    }\n\n    fun markHistory')
edit(b/"UserDictionary.kt",
    '        val ext=sourceName.substringAfterLast(\'.\',\"\").lowercase(Locale.ROOT)\n        require(ext in setOf("txt","tsv","csv"))',
    '        val ext=sourceName.substringAfterLast(\'.\',\"\").lowercase(Locale.ROOT)\n        if(ext=="mdx" || ext=="mdd") return MdxCatalog.importFile(app,uri,sourceName)\n        require(ext in setOf("txt","tsv","csv"))')
(b/"MdxCatalog.kt").write_text(r'''package com.galaxy.airviewdictionary.data.local.dictionary

import android.content.Context
import android.net.Uri
import android.util.Log
import java.io.File
import java.nio.file.Path
import java.util.LinkedHashMap

/** Open local, user-supplied MDict files. Does not bypass DRM or download books. */
internal object MdxCatalog {
    private val cache=object:LinkedHashMap<String,Any>(3,0.75f,true) {
        override fun removeEldestEntry(eldest:MutableMap.MutableEntry<String,Any>?)=size>3
    }
    private val names=listOf(
        "tokyo.northside.mdict.MDictDictionary",
        "io.github.eb4j.mdict.MDictDictionary",
        "io.github.eb4j.mdict4j.MDictDictionary",
        "io.github.eb4j.mdict.MdictDictionary",
        "org.eb4j.mdict.MDictDictionary"
    )
    private fun cls():Class<*> =
        names.firstNotNullOfOrNull { runCatching{Class.forName(it)}.getOrNull() }
            ?: error("不支持的 MDX 解析器版本")
    private fun dir(ctx:Context)=File(ctx.filesDir,"mdict").apply{mkdirs()}
    fun importFile(ctx:Context,uri:Uri,name:String):Int {
        val basename=name.substringAfterLast('/').substringAfterLast('\\')
            .replace(Regex("[^a-zA-Z0-9_ .()\\-\\p{L}]"),"_").take(180)
        require(basename.endsWith(".mdx",true)||basename.endsWith(".mdd",true)){"只支持 MDX/MDD"}
        val target=File(dir(ctx),basename)
        val tmp=File(dir(ctx),".import-${System.nanoTime()}.${basename.substringAfterLast('.')}")
        try {
            (ctx.contentResolver.openInputStream(uri)?:error("无法打开")).use { input->
                tmp.outputStream().buffered().use{out->
                    val buf=ByteArray(131072)
                    var total=0L
                    while(true) {
                        val n=input.read(buf);if(n<0)break
                        total+=n
                        if(total>2147483648L)error("词典超过此版本支持的 2 GiB")
                        out.write(buf,0,n)
                    }
                }
            }
            if(basename.endsWith(".mdx",true)) {
                cls().getMethod("loadDictionary",Path::class.java).invoke(null,tmp.toPath())
            }
            if(target.exists())check(target.delete())
            check(tmp.renameTo(target)){"保存失败"}
            synchronized(cache){cache.remove(target.absolutePath)}
            return 1
        }finally{tmp.delete()}
    }
    private fun reader(file:File):Any {
        synchronized(cache){cache[file.absolutePath]?.let{return it}}
        val obj=cls().getMethod("loadDictionary",Path::class.java)
            .invoke(null,file.toPath())
        synchronized(cache){cache[file.absolutePath]=obj}
        return obj
    }
    /** Resolve optional same-name MDD images/CSS/audio for a local MDX entry. */
    fun asset(ctx:Context,source:String,requestPath:String):ByteArray? {
        val base=source.substringBeforeLast('.')
        val file=File(dir(ctx),"$base.mdd")
        if(!file.exists())return null
        val raw=requestPath.substringBefore('?').trimStart('/')
        if(raw.isBlank()||raw.length>250||".." in raw)return null
        return runCatching {
            val reader=cls().getMethod("loadDictionaryData",Path::class.java)
                .invoke(null,file.toPath())
            val method=reader.javaClass.getMethod("getEntries",String::class.java)
            val keys=listOf("/$raw","\\\\\${raw.replace('/','\\\\')}","$raw")
            var content:ByteArray?=null
            for(key in keys) {
                val entries=(method.invoke(reader,key) as? List<*>).orEmpty()
                val item=entries.firstOrNull() as? Map.Entry<*,*> ?: continue
                val dataMethod=reader.javaClass.methods.firstOrNull {
                    it.name=="getData" && it.parameterCount==1
                } ?: break
                val data=dataMethod.invoke(reader,item.value) as? ByteArray
                if(data!=null && data.size<=8*1024*1024) {content=data;break}
            }
            content
        }.getOrNull()
    }

    fun lookup(ctx:Context,word:String):DictionaryEntry? {
        if(word.isBlank()||word.length>120)return null
        for(file in dir(ctx).listFiles().orEmpty().filter {it.extension.equals("mdx",true)}) {
            try {
                val obj=reader(file)
                val entries=(obj.javaClass.getMethod("readArticles",String::class.java)
                    .invoke(obj,word) as? List<*>).orEmpty()
                val first=entries.firstOrNull() as? Map.Entry<*,*>
                val data=first?.value?.toString().orEmpty().take(120000)
                if(data.isNotBlank())return DictionaryEntry(word,data,file.name)
            }catch(e:Exception){Log.w("MDX","Lookup failed: ${file.name}",e)}
        }
        return null
    }
}
''',"utf8")
print("MDX/MDD importer integrated")
