package dev.jinsfoni.photobook.ui.screens.settings

import dev.jinsfoni.photobook.core.design.ThemeMode
import dev.jinsfoni.photobook.data.prefs.FakeSessionStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

/** SettingsViewModel:档案列表/激活/删除、主题三态、语言存档(API<33 路径)。 */
@OptIn(ExperimentalCoroutinesApi::class)
class SettingsViewModelTest {

    private val dispatcher = StandardTestDispatcher()
    private lateinit var session: FakeSessionStore
    private lateinit var vm: SettingsViewModel
    private var recreated = 0
    private var localeTagsSet: String? = null

    /** 桩:模拟 API<33(currentTags 恒 null = 平台不支持 per-app locale)。 */
    private val fakeLocaleCtl = object : LocaleManagerApi {
        override fun currentTags(): String? = null
        override fun setTags(tag: String) { localeTagsSet = tag }
    }

    @Before
    fun setUp() {
        Dispatchers.setMain(dispatcher)
        session = FakeSessionStore()
        recreated = 0
        localeTagsSet = null
        vm = SettingsViewModel(session, fakeLocaleCtl)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    /** stateIn(WhileSubscribed) 需订阅才开始计算;backgroundScope 随测试结束自动取消。 */
    private fun kotlinx.coroutines.test.TestScope.watchState() =
        backgroundScope.launch { vm.state.collect { } }

    @Test
    fun `档案列表与激活态来自 session`() = runTest(dispatcher.scheduler) {
        watchState()
        session.addProfile("http://a:8000", "tok-a", "alice")
        session.addProfile("http://b:8000", "tok-b", "bob")
        val firstId = session.profilesFlow.value.first().id
        vm.activateProfile(firstId)
        dispatcher.scheduler.advanceUntilIdle()

        assertEquals(2, vm.state.value.profiles.size)
        assertEquals(firstId, vm.state.value.activeProfileId)
    }

    @Test
    fun `removeProfile 删活动档案顺延`() = runTest(dispatcher.scheduler) {
        watchState()
        val a = session.addProfile("http://a:8000", "tok-a", "alice")
        val b = session.addProfile("http://b:8000", "tok-b", "bob")
        vm.removeProfile(b.id)
        dispatcher.scheduler.advanceUntilIdle()

        assertEquals(1, vm.state.value.profiles.size)
        assertEquals(a.id, vm.state.value.activeProfileId)
    }

    @Test
    fun `removeProfile 删光后档案为空`() = runTest(dispatcher.scheduler) {
        watchState()
        val a = session.addProfile("http://a:8000", "tok-a", "alice")
        vm.removeProfile(a.id)
        dispatcher.scheduler.advanceUntilIdle()

        assertEquals(0, vm.state.value.profiles.size)
        assertNull(vm.state.value.activeProfileId)
    }

    @Test
    fun `setTheme 三态往返并写回 session`() = runTest(dispatcher.scheduler) {
        watchState()
        vm.setTheme(ThemeMode.BLUR)
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ThemeMode.BLUR, vm.state.value.theme)
        assertEquals(ThemeMode.BLUR, session.themeFlow.value)

        vm.setTheme(ThemeMode.DARK)
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ThemeMode.DARK, vm.state.value.theme)
    }

    @Test
    fun `setLocale 平台不支持时走存档并触发 recreate`() = runTest(dispatcher.scheduler) {
        vm.setLocale("zh-TW") { recreated++ }
        dispatcher.scheduler.advanceUntilIdle()

        assertEquals("zh-TW", session.localeFlow.value)
        assertEquals(1, recreated)
        assertNull(localeTagsSet) // 未走系统 per-app locale
    }
}
