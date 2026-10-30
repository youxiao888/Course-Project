#!/usr/bin/env python3
"""Fix mdict4j 0.4.0 API: loadDictionary/loadDictionaryData take String, not Path.
Fail early on an MDX parse error before copying multi-gigabyte MDD archives.
"""
from pathlib import Path

base=Path("app/src/main/java/com/galaxy/airviewdictionary/data/local/dictionary")
def replace_once(p,old,new):
    p=Path(p)
    data=p.read_text(encoding="utf-8")
    count=data.count(old)
    if count!=1:raise AssertionError(f"{p}: anchor count {count}: {old[:140]!r}")
    p.write_text(data.replace(old,new,1),encoding="utf-8")
    print("patched",p)

mdx=base/"MdxCatalog.kt"
replace_once(mdx,
'''val factory=runCatching {
            cls().getMethod("loadDictionaryData",Path::class.java)
        }.getOrNull() ?: return null''',
'''val factory=runCatching {
            cls().getMethod("loadDictionaryData",String::class.java)
        }.getOrNull() ?: return null''')
replace_once(mdx,
'''factory.invoke(null,file.toPath())''',
'''factory.invoke(null,file.absolutePath)''')
replace_once(mdx,
'''val obj=cls().getMethod("loadDictionary",Path::class.java)
            .invoke(null,file.toPath())''',
'''// Use the actual public String API from mdict4j 0.4.0.
        val obj=io.github.eb4j.mdict.MDictDictionary.loadDictionary(file.absolutePath)''')
# match MDX library method via direct class link in code - missing Java API fails Kotlin compilation.
imp=base/"OxfordFolderImporter.kt"
replace_once(imp,
'''val files=findFiles(ctx,tree)''',
'''// Validate the comparatively small MDX first, before copying GB-sized MDDs.
        val files=findFiles(ctx,tree).sortedWith(
            compareBy<Item> { if(it.relative.endsWith(".mdx",true))0 else 1 }
                .thenBy { it.relative.lowercase() }
        )''')
replace_once(imp,
'''                if(item.size>=0 && fileBytes!=item.size)
                    error("文件复制不完整："+item.relative)
                onProgress''',
'''                if(item.size>=0 && fileBytes!=item.size)
                    error("文件复制不完整："+item.relative)
                if(item.relative.endsWith(".mdx",true)) {
                    try {
                        val dictionary=io.github.eb4j.mdict.MDictDictionary.loadDictionary(dest.absolutePath)
                        check(dictionary.isMdx) {"主词典文件格式不正确"}
                        // Exercise the actual query API before copying large resources.
                        dictionary.readArticles("book")
                    }catch(e:Exception){
                        error("MDX 主词典验证失败（资源文件尚未复制）："+
                            (e.cause?.message ?: e.message))
                    }
                }
                onProgress''')
replace_once(imp,
'''            val cls=Class.forName("io.github.eb4j.mdict.MDictDictionary")
            cls.getMethod("loadDictionary",Path::class.java).invoke(null,mdx.toPath())''',
'''            // Recheck that a complete MDX is present, already validated first.
            check(mdx.isFile && mdx.length()>0L) {"主词典复制不完整"}''')
# Real ABI signature regression tests, independent from a user-supplied paid dictionary.
t=Path("app/src/test/java/com/galaxy/airviewdictionary/data/local/dictionary/Mdict4jApiTest.kt")
t.parent.mkdir(parents=True,exist_ok=True)
t.write_text(r'''package com.galaxy.airviewdictionary.data.local.dictionary

import io.github.eb4j.mdict.MDictDictionary
import org.junit.Assert.*
import org.junit.Test

/** Protect against the V2.2 crash: loadDictionary(Path) does not exist in mdict4j 0.4.0. */
class Mdict4jApiTest {
    @Test fun loaderUsesActualStringPathApi() {
        val clazz=MDictDictionary::class.java
        val load=clazz.getMethod("loadDictionary",String::class.java)
        val loadResource=clazz.getMethod("loadDictionaryData",String::class.java)
        assertTrue(java.lang.reflect.Modifier.isStatic(load.modifiers))
        assertTrue(java.lang.reflect.Modifier.isStatic(loadResource.modifiers))
        assertEquals(clazz,load.returnType)
        assertEquals(clazz,loadResource.returnType)
    }

    @Test fun queryAndResourceAccessMethodsExist() {
        val clazz=MDictDictionary::class.java
        assertNotNull(clazz.getMethod("readArticles",String::class.java))
        assertNotNull(clazz.getMethod("getEntries",String::class.java))
        assertEquals(ByteArray::class.java,clazz.getMethod("getData",java.lang.Long::class.java).returnType)
    }
}
''',encoding="utf-8")
print("MDict 0.4.0 path ABI fixed and regression tests installed")
