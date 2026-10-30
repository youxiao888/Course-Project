#!/usr/bin/env python3
"""Fix MDX collection discoverability and all numbered MDD/CSS/image resources."""
from pathlib import Path
b=Path("app/src/main/java/com/galaxy/airviewdictionary")
p=b/"data/local/dictionary/MdxCatalog.kt"
s=p.read_text("utf8")
def one(old,new):
 global s
 n=s.count(old)
 if n!=1:raise RuntimeError("MdxCatalog anchor matches="+str(n)+": "+old[:90])
 s=s.replace(old,new,1)
one("size>3","size>10")
idx=s.index("    /** Resolve optional same-name MDD")
end=s.index("    fun lookup(ctx:Context,word:String):DictionaryEntry?",idx)
s=s[:idx]+r'''    /** Discover legacy single-file imports plus atomic whole-folder collections. */
    private fun mdxFiles(ctx:Context):List<File> {
        val root=dir(ctx)
        val old=root.listFiles().orEmpty().filter{it.isFile && it.extension.equals("mdx",true)}
        val folders=File(root,"collections").listFiles().orEmpty().filter{it.isDirectory}
        val imported=folders.flatMap { collection ->
            collection.walkTopDown().filter{it.isFile && it.extension.equals("mdx",true)}
                .take(50).toList()
        }
        return imported+old
    }

    /** Same-directory assets first, then multiple oaldpe.mdd/oaldpe.N.mdd archives. */
    fun asset(ctx:Context,source:String,requestPath:String):ByteArray? {
        val root=dir(ctx).canonicalFile
        val mdx=File(root,source).canonicalFile
        if(!mdx.path.startsWith(root.path+File.separator) || !mdx.isFile)return null
        val folder=mdx.parentFile ?: return null
        val raw=requestPath.substringBefore('?').trimStart('/')
        if(raw.isBlank() || raw.length>260 || ".." in raw)return null
        val ext=raw.substringAfterLast('.',"").lowercase()
        if(ext !in setOf("css","png","jpg","jpeg","gif","svg","webp",
                "woff","woff2","ttf","otf","mp3","wav","ogg","ico")) return null
        val local=File(folder,raw).canonicalFile
        if(local.path.startsWith(folder.path+File.separator) &&
           local.isFile && local.length()<=16L*1024*1024) {
            return runCatching{local.readBytes()}.getOrNull()
        }
        val base=mdx.nameWithoutExtension
        val archives=folder.listFiles().orEmpty().filter{
            it.isFile && OxfordMddNames.matches(base,it.name)
        }.sortedWith(compareBy{OxfordMddNames.index(base,it.name)})
        val factory=runCatching {
            cls().getMethod("loadDictionaryData",Path::class.java)
        }.getOrNull() ?: return null
        val keys=listOf("/"+raw,92.toChar().toString()+raw.replace('/',92.toChar()),raw)
        for(file in archives) {
            try {
                val reader=synchronized(cache) {
                    cache[file.absolutePath] ?: factory.invoke(null,file.toPath()).also{
                        cache[file.absolutePath]=it
                    }
                }
                val find=reader.javaClass.getMethod("getEntries",String::class.java)
                val get=reader.javaClass.methods.firstOrNull{it.name=="getData" && it.parameterCount==1}
                    ?: continue
                for(key in keys) {
                    val entries=(find.invoke(reader,key) as? List<*>).orEmpty()
                    val first=entries.firstOrNull() as? Map.Entry<*,*> ?:continue
                    val bytes=get.invoke(reader,first.value) as? ByteArray ?:continue
                    if(bytes.size<=16*1024*1024)return bytes
                }
            }catch(e:Exception){Log.w("MDX","MDD resource lookup failed: "+file.name,e)}
        }
        return null
    }

'''+s[end:]
one(
'''        for(file in dir(ctx).listFiles().orEmpty().filter {it.extension.equals("mdx",true)}) {''',
'''        for(file in mdxFiles(ctx)) {''')
one(
'''if(data.isNotBlank())return DictionaryEntry(word,data,file.name)''',
'''if(data.isNotBlank()) {
                    val source=file.relativeTo(dir(ctx)).path.replace(File.separatorChar,'/')
                    return DictionaryEntry(word,data,source)
                }''')
p.write_text(s,"utf8")

(b/"data/local/dictionary/OxfordMddNames.kt").write_text(r'''package com.galaxy.airviewdictionary.data.local.dictionary

/** Pure Kotlin MDD archive matching: oaldpe.mdd, oaldpe.1.mdd, ... */
internal object OxfordMddNames {
    fun index(stem:String, filename:String):Int {
        val prefix=stem.lowercase()
        val name=filename.lowercase()
        if(name==prefix+".mdd")return 0
        if(!name.startsWith(prefix+".") || !name.endsWith(".mdd"))return -1
        val middle=name.substring(prefix.length+1,name.length-4)
        return middle.toIntOrNull()?.takeIf{it>0} ?: -1
    }
    fun matches(stem:String, filename:String):Boolean=index(stem,filename)>=0
}
''',"utf8")

p=b/"../../test/java/com/galaxy/airviewdictionary/data/local/dictionary/OxfordMddNamesTest.kt"
# Resolve to app/src/test directly, not java/main.
p=Path("app/src/test/java/com/galaxy/airviewdictionary/data/local/dictionary/OxfordMddNamesTest.kt")
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(r'''package com.galaxy.airviewdictionary.data.local.dictionary

import org.junit.Test
import org.junit.Assert.*

class OxfordMddNamesTest {
    @Test fun oxfordFourArchives() {
        val names=listOf("oaldpe.mdd","oaldpe.1.mdd","oaldpe.2.mdd","oaldpe.3.mdd")
        assertTrue(names.all{OxfordMddNames.matches("oaldpe",it)})
        assertEquals(listOf(0,1,2,3),names.map{OxfordMddNames.index("oaldpe",it)})
    }
    @Test fun unrelatedFilesAreNotMddArchives(){
        assertFalse(OxfordMddNames.matches("oaldpe","oaldpe.mdx"))
        assertFalse(OxfordMddNames.matches("oaldpe","oaldpe.css"))
        assertFalse(OxfordMddNames.matches("oaldpe","other.1.mdd"))
        assertFalse(OxfordMddNames.matches("oaldpe","oaldpe.-1.mdd"))
    }
    @Test fun caseInsensitive(){
        assertTrue(OxfordMddNames.matches("OALDPE","oaldpe.3.MDD"))
    }
}
''',"utf8")
print("Collection path lookup and numbered MDD resources patch complete")
