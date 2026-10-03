package dev.jinsfoni.photobook.data.repo

import dev.jinsfoni.photobook.data.prefs.SessionStoreApi
import dev.jinsfoni.photobook.data.remote.MobileApi
import dev.jinsfoni.photobook.data.remote.safeCall
import dev.jinsfoni.photobook.ui.models.SearchResults
import javax.inject.Inject
import javax.inject.Singleton

/** 站内搜索:三段结果(模特/写真/标签),URL 拼装与列表同规则。 */
@Singleton
class SearchRepository @Inject constructor(
    private val api: MobileApi,
    private val session: SessionStoreApi,
) {

    suspend fun search(q: String): SearchResults {
        val dto = safeCall { api.search(q.trim()) }
        val base = session.currentBaseUrl()
        return SearchResults(
            q = dto.q,
            models = dto.models.map { it.toSearchCard(base) },
            collections = dto.collections.map { it.toModel(base) },
            tags = dto.tags,
        )
    }
}
