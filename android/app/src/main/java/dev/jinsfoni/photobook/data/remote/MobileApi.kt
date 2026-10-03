package dev.jinsfoni.photobook.data.remote

import dev.jinsfoni.photobook.data.remote.dto.CollectionsPageDto
import dev.jinsfoni.photobook.data.remote.dto.DiscoverDto
import dev.jinsfoni.photobook.data.remote.dto.FavoriteRequestDto
import dev.jinsfoni.photobook.data.remote.dto.FavoriteResultDto
import dev.jinsfoni.photobook.data.remote.dto.FavoritesDto
import dev.jinsfoni.photobook.data.remote.dto.LoginRequestDto
import dev.jinsfoni.photobook.data.remote.dto.LoginResponseDto
import dev.jinsfoni.photobook.data.remote.dto.MeDto
import dev.jinsfoni.photobook.data.remote.dto.CollectionDto
import dev.jinsfoni.photobook.data.remote.dto.ModelDetailDto
import dev.jinsfoni.photobook.data.remote.dto.ModelsPageDto
import dev.jinsfoni.photobook.data.remote.dto.SearchResultDto
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/** 服务端 /api/mobile 契约(见 app/routers/mobile_api.py)。 */
interface MobileApi {

    @POST("auth/login")
    suspend fun login(@Body body: LoginRequestDto): LoginResponseDto

    @GET("auth/me")
    suspend fun me(): MeDto

    @GET("discover")
    suspend fun discover(): DiscoverDto

    @GET("collections")
    suspend fun collections(
        @Query("tag") tag: String? = null,
        @Query("page") page: Int = 1,
        @Query("pageSize") pageSize: Int = 20,
        @Query("sort") sort: String = "latest",
    ): CollectionsPageDto

    @GET("collections/{slug}")
    suspend fun collection(@Path("slug") slug: String): CollectionDto

    @GET("models")
    suspend fun models(@Query("featured") featured: String? = null): ModelsPageDto

    @GET("models/{slug}")
    suspend fun model(@Path("slug") slug: String): ModelDetailDto

    @GET("search")
    suspend fun search(@Query("q") q: String): SearchResultDto

    @GET("favorites")
    suspend fun favorites(): FavoritesDto

    @POST("favorites")
    suspend fun toggleFavorite(@Body body: FavoriteRequestDto): FavoriteResultDto
}
