#!/usr/bin/env python3
"""Fix Android RIPEMD128 algorithm missing from mdict4j encrypted-index decryption."""
from pathlib import Path

gradle=Path("app/build.gradle.kts")
s=gradle.read_text("utf8")
needle='    implementation("tokyo.northside:mdict4j:0.4.0") {'
assert s.count(needle)==1
s=s.replace(needle,'''    // RIPEMD128Digest from Bouncy Castle lightweight API.
    // Do not register BouncyCastleProvider under "BC": Android's own BC
    // provider may already occupy that name but lack RIPEMD128.
    implementation("org.bouncycastle:bcprov-jdk15on:1.70")
'''+needle,1)
gradle.write_text(s,"utf8")

runtime=Path("app/src/main/java/com/galaxy/airviewdictionary/data/local/dictionary/AndroidMdictRuntime.kt")
runtime.write_text(r'''package com.galaxy.airviewdictionary.data.local.dictionary

import java.security.MessageDigest
import java.security.MessageDigestSpi
import java.security.Provider
import java.security.Security
import java.security.NoSuchAlgorithmException
import org.bouncycastle.crypto.digests.RIPEMD128Digest

/**
 * Isolated RIPEMD-128 provider for MDict 2.x encrypted *index blocks*.
 *
 * mdict4j 0.4.0 calls MessageDigest.getInstance("RIPEMD128") while
 * decompressing an index whose Encrypted flag includes bit 0x2.
 * Android's platform "BC" provider may exist without this digest.
 * Register only this digest under a unique provider name rather than
 * replacing Android's system BC provider or changing cryptography globally.
 */
class MDictRIPEMD128Spi : MessageDigestSpi() {
    private val digest = RIPEMD128Digest()
    override fun engineUpdate(input: Byte) {
        digest.update(input)
    }
    override fun engineUpdate(input: ByteArray, offset: Int, len: Int) {
        digest.update(input, offset, len)
    }
    override fun engineDigest(): ByteArray {
        val result = ByteArray(16)
        digest.doFinal(result, 0)
        return result
    }
    override fun engineReset() {
        digest.reset()
    }
    override fun engineGetDigestLength(): Int = 16
}

internal object AndroidMdictRuntime {
    private const val RIPEMD_PROVIDER = "ScreenTranslator-MDict-RIPEMD128"
    @Volatile private var initialized = false

    @Synchronized
    fun ensureReady() {
        if (initialized) return

        // XML parsing required by mdict4j's dictionary header parser.
        System.setProperty(
            "javax.xml.stream.XMLInputFactory",
            "com.fasterxml.aalto.stax.InputFactoryImpl"
        )
        System.setProperty(
            "javax.xml.stream.XMLOutputFactory",
            "com.fasterxml.aalto.stax.OutputFactoryImpl"
        )

        // Never remove, rename or override Android's built-in BC provider.
        if (Security.getProvider(RIPEMD_PROVIDER) == null) {
            val provider = object: Provider(
                RIPEMD_PROVIDER, 1.0, "RIPEMD-128 for MDict encrypted index"
            ) {
                init {
                    put(
                        "MessageDigest.RIPEMD128",
                        MDictRIPEMD128Spi::class.java.name
                    )
                }
            }
            val index = Security.addProvider(provider)
            check(index > 0 || Security.getProvider(RIPEMD_PROVIDER) != null) {
                "Android blocked RIPEMD128 provider registration"
            }
        }

        // Fail early rather than reporting a vague Decryption failed after copying.
        val md = try {
            MessageDigest.getInstance("RIPEMD128")
        } catch (e: NoSuchAlgorithmException) {
            throw IllegalStateException(
                "Android RIPEMD128 provider cannot be loaded", e
            )
        }
        check(md.digest(ByteArray(0)).toHex() ==
            "cdf26213a150dc3ecb610f18f6b38b46") {
            "RIPEMD128 self-check failed: decoder cannot be trusted"
        }
        initialized = true
    }

    private fun ByteArray.toHex():String =
        joinToString("") { "%02x".format(it.toInt() and 0xff) }
}
''',"utf8")

test=Path("app/src/androidTest/java/com/galaxy/airviewdictionary/data/local/dictionary/AndroidMdictRuntimeTest.kt")
s=test.read_text("utf8")
needle='''    @Test fun mdictLibraryLoadsOnAndroidWithoutMissingClassErrors() {'''
assert s.count(needle)==1
s=s.replace(needle,r'''    @Test fun encryptedMdictIndexRIPEMD128WorksOnAndroid() {
        // This exact branch previously threw MDException("Decryption failed.")
        // because mdict4j's SHA API requested "RIPEMD128" via JCA.
        AndroidMdictRuntime.ensureReady()
        val digest=java.security.MessageDigest.getInstance("RIPEMD128")
        val bytes=digest.digest(ByteArray(0))
        assertEquals(
            "cdf26213a150dc3ecb610f18f6b38b46",
            bytes.joinToString("") { "%02x".format(it.toInt() and 0xff) }
        )
        val encrypted=byteArrayOf(1,2,3,4,5,6,7,8)
        val salt=byteArrayOf(0x01,0x00,0x10,0x33)
        val result=io.github.eb4j.mdict.io.MDictUtils.decryptKeyIndex(encrypted,salt)
        assertEquals(encrypted.size,result.size)
        assertFalse(encrypted.contentEquals(result))
    }

    @Test fun providerInitializesMoreThanOnceWithoutChangingDigest() {
        AndroidMdictRuntime.ensureReady()
        val before=java.security.Security.getProviders().size
        AndroidMdictRuntime.ensureReady()
        val after=java.security.Security.getProviders().size
        assertEquals(before,after)
    }

'''+needle,1)
test.write_text(s,"utf8")
print("RIPEMD128 Android JCA provider and encrypted-index decoder regression tests added.")
