#!/usr/bin/env python3
"""Android runtime StAX integration and instrumented regression test."""
from pathlib import Path
gradle=Path("app/build.gradle.kts")
t=gradle.read_text("utf8")
anchor='    implementation("tokyo.northside:mdict4j:0.4.0") {'
if t.count(anchor)!=1:raise RuntimeError("mdict4j dependency missing")
t=t.replace(anchor,'''    // Android does not ship StAX; mdict4j's Jackson XML requires both
    // the javax.xml.stream API and a concrete XMLInputFactory provider.
    implementation("javax.xml.stream:stax-api:1.0-2")
    implementation("com.fasterxml:aalto-xml:1.3.4")
    implementation("org.codehaus.woodstox:stax2-api:4.2.2")
    implementation("tokyo.northside:mdict4j:0.4.0") {''',1)
# Preserve the factory provider registration when merged from JAR resources.
needle='''        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }'''
if t.count(needle)!=1:raise RuntimeError("packaging resources anchor missing")
t=t.replace(needle,'''        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
            pickFirsts += "META-INF/services/javax.xml.stream.XMLInputFactory"
            pickFirsts += "META-INF/services/javax.xml.stream.XMLOutputFactory"
        }''')
gradle.write_text(t,"utf8")
test=Path("app/src/androidTest/java/com/galaxy/airviewdictionary/data/local/dictionary/AndroidMdictRuntimeTest.kt")
test.parent.mkdir(parents=True,exist_ok=True)
test.write_text(r'''package com.galaxy.airviewdictionary.data.local.dictionary

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.fasterxml.jackson.dataformat.xml.XmlMapper
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.Assert.*
import javax.xml.stream.XMLInputFactory
import java.io.StringReader

/** Tests actual ART/Dalvik class resolution; JVM-only tests could not catch this. */
@RunWith(AndroidJUnit4::class)
class AndroidMdictRuntimeTest {
    @Test fun androidHasStaxAndCanParseXml() {
        val clazz=Class.forName("javax.xml.stream.XMLInputFactory")
        assertNotNull(clazz)
        System.setProperty("javax.xml.stream.XMLInputFactory",
            "com.fasterxml.aalto.stax.InputFactoryImpl")
        val factory=XMLInputFactory.newInstance()
        assertNotNull(factory)
        val parser=factory.createXMLStreamReader(StringReader("<dict><name>book</name></dict>"))
        var found=false
        try {
            while(parser.hasNext()) {
                parser.next()
                if(parser.isStartElement && parser.localName=="name") found=true
            }
        } finally { parser.close() }
        assertTrue("XML stream parser could not read MDX-like header",found)
    }

    @Test fun androidJacksonXmlFactoryActuallyInitializes() {
        System.setProperty("javax.xml.stream.XMLInputFactory",
            "com.fasterxml.aalto.stax.InputFactoryImpl")
        System.setProperty("javax.xml.stream.XMLOutputFactory",
            "com.fasterxml.aalto.stax.OutputFactoryImpl")
        val mapper=XmlMapper()
        val node=mapper.readTree("<dict><word>book</word></dict>")
        assertEquals("book",node.path("word").asText())
    }

    @Test fun mdictLibraryLoadsOnAndroidWithoutMissingClassErrors() {
        // Exercise MDictDictionary's Android class initialization.
        val clazz=Class.forName("io.github.eb4j.mdict.MDictDictionary")
        assertNotNull(clazz.getMethod("loadDictionary",String::class.java))
        assertNotNull(clazz.getMethod("readArticles",String::class.java))
    }
}
''',"utf8")

stax=Path("app/src/main/java/com/galaxy/airviewdictionary/data/local/dictionary/AndroidMdictRuntime.kt")
stax.write_text(r'''package com.galaxy.airviewdictionary.data.local.dictionary

/** Android does not bundle a StAX provider. Configure the embedded Aalto
 * provider before loading *any* MDX or MDD. This is also exercised on emulator.
 */
internal object AndroidMdictRuntime {
    @Synchronized fun ensureReady() {
        System.setProperty("javax.xml.stream.XMLInputFactory",
            "com.fasterxml.aalto.stax.InputFactoryImpl")
        System.setProperty("javax.xml.stream.XMLOutputFactory",
            "com.fasterxml.aalto.stax.OutputFactoryImpl")
    }
}
''',"utf8")

catalog=Path("app/src/main/java/com/galaxy/airviewdictionary/data/local/dictionary/MdxCatalog.kt")
v=catalog.read_text("utf8")
old='''    private fun cls():Class<*> =
        names.firstNotNullOfOrNull { runCatching{Class.forName(it)}.getOrNull() }
            ?: error("不支持的 MDX 解析器版本")'''
new='''    private fun cls():Class<*> {
        AndroidMdictRuntime.ensureReady()
        return names.firstNotNullOfOrNull { runCatching{Class.forName(it)}.getOrNull() }
            ?: error("不支持的 MDX 解析器版本")
    }'''
if v.count(old)!=1:raise RuntimeError("MDX parser initialization anchor mismatch")
catalog.write_text(v.replace(old,new,1),"utf8")

folder=Path("app/src/main/java/com/galaxy/airviewdictionary/data/local/dictionary/OxfordFolderImporter.kt")
v=folder.read_text("utf8")
old='''                    val cls=Class.forName("io.github.eb4j.mdict.MDictDictionary")'''
new='''                    AndroidMdictRuntime.ensureReady()
                    val cls=Class.forName("io.github.eb4j.mdict.MDictDictionary")'''
if v.count(old)!=1:raise RuntimeError("Oxford folder parser initialization anchor mismatch")
folder.write_text(v.replace(old,new,1),"utf8")

# Test the actual production setup rather than a test-only property hack.
testtext=test.read_text("utf8")
testtext=testtext.replace('''        System.setProperty("javax.xml.stream.XMLInputFactory",
            "com.fasterxml.aalto.stax.InputFactoryImpl")''',
'''        AndroidMdictRuntime.ensureReady()''')
testtext=testtext.replace('''        System.setProperty("javax.xml.stream.XMLInputFactory",
            "com.fasterxml.aalto.stax.InputFactoryImpl")
        System.setProperty("javax.xml.stream.XMLOutputFactory",
            "com.fasterxml.aalto.stax.OutputFactoryImpl")''',
'''        AndroidMdictRuntime.ensureReady()''')
test.write_text(testtext,"utf8")
print("Android StAX runtime dependencies and device instrumentation tests created")
