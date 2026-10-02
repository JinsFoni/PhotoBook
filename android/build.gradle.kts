// AGP 9.4.1 的插件 marker 会把内嵌 KGP(2.2.10)带上 classpath 且版本不可见,
// 因此 kotlin 系插件不用 plugins{} marker,而是在 buildscript 显式钉 2.4.20
// (conflict resolution 取最高版本),模块内按 id 无版本号应用。
buildscript {
    dependencies {
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:2.4.20")
        classpath("org.jetbrains.kotlin:compose-compiler-gradle-plugin:2.4.20")
        classpath("org.jetbrains.kotlin:kotlin-serialization:2.4.20")
    }
}

plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.ksp) apply false
    alias(libs.plugins.hilt) apply false
}
