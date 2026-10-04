package dev.jinsfoni.photobook.data.prefs

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.assertNull
import dev.jinsfoni.photobook.core.design.ThemeMode
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Test

/** M3 多档案存储语义:增/切/删/主题/语言。 */
class SessionStoreProfilesTest {

    private fun store() = FakeSessionStore().apply {
        // 预置一个旧式单服务器档案(迁移来源)
    }

    @Test
    fun `addProfile 激活新档案并可切换回来`() = runTest {
        val s = store()
        val a = s.addProfile("http://a:8000", "tok-a", "alice")
        val b = s.addProfile("http://b:8000", "tok-b", "bob")

        assertEquals(b.id, s.activeProfileId.first())
        assertEquals("tok-b", s.token.first())

        s.setActiveProfile(a.id)
        assertEquals(a.id, s.activeProfileId.first())
        assertEquals("http://a:8000", s.baseUrl.first())
        assertEquals("tok-a", s.token.first())
    }

    @Test
    fun `addProfile 同地址去重覆盖`() = runTest {
        val s = store()
        val first = s.addProfile("http://a:8000/", "tok-1", "alice")
        val again = s.addProfile("http://a:8000", "tok-2", "alice2")

        assertEquals(first.id, again.id)
        assertEquals(1, s.profiles.first().size)
        assertEquals("tok-2", s.token.first())
    }

    @Test
    fun `removeProfile 删活动档案顺延到下一个`() = runTest {
        val s = store()
        val a = s.addProfile("http://a:8000", "tok-a", "alice")
        val b = s.addProfile("http://b:8000", "tok-b", "bob")

        s.removeProfile(b.id)
        assertEquals(1, s.profiles.first().size)
        assertEquals(a.id, s.activeProfileId.first())
        assertEquals("tok-a", s.token.first())

        // 删光 = 登出态
        s.removeProfile(a.id)
        assertTrue(s.profiles.first().isEmpty())
        assertNull(s.activeProfileId.first())
        assertNull(s.token.first())
    }

    @Test
    fun `saveSession 与 clearSession 只影响活动档案`() = runTest {
        val s = store()
        val a = s.addProfile("http://a:8000", "tok-a", "alice")
        val b = s.addProfile("http://b:8000", "tok-b", "bob")

        s.setActiveProfile(a.id)
        s.saveSession("tok-a2", "alice")
        assertEquals("tok-a2", s.profiles.first().first { it.id == a.id }.token)
        assertEquals("tok-b", s.profiles.first().first { it.id == b.id }.token)

        s.clearSession()
        assertTrue(s.profiles.first().first { it.id == a.id }.token.isEmpty())
    }

    @Test
    fun `主题与语言持久化往返`() = runTest {
        val s = store()
        s.saveTheme(ThemeMode.BLUR)
        assertEquals(ThemeMode.BLUR, s.theme.first())
        s.saveTheme(ThemeMode.DARK)
        assertEquals(ThemeMode.DARK, s.theme.first())

        s.saveLocale("zh-TW")
        assertEquals("zh-TW", s.locale.first())
        s.saveLocale("")
        assertTrue(s.locale.first().isEmpty())
    }
}
