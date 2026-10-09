package dev.jinsfoni.photobook.data.repo

import java.io.File
import java.nio.file.Files

/** 单测用 CacheDirProvider:每次调用给独立临时目录(JVM 测试无 Android Context)。 */
fun tempCacheDir(): CacheDirProvider {
    val dir: File = Files.createTempDirectory("photobook-test-cache").toFile()
    return CacheDirProvider { dir }
}
