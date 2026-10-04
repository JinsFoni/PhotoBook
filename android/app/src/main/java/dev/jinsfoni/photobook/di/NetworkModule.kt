package dev.jinsfoni.photobook.di

import coil3.ImageLoader
import coil3.network.okhttp.OkHttpNetworkFetcherFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import dev.jinsfoni.photobook.data.prefs.SessionStore
import dev.jinsfoni.photobook.data.remote.ApiErrors
import dev.jinsfoni.photobook.data.remote.AuthInterceptor
import dev.jinsfoni.photobook.data.remote.HostSelectionInterceptor
import dev.jinsfoni.photobook.data.remote.MobileApi
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideJson(): Json = ApiErrors.json

    @Provides
    @Singleton
    fun provideSessionStoreApi(store: SessionStore): dev.jinsfoni.photobook.data.prefs.SessionStoreApi = store

    @Provides
    @Singleton
    fun provideOkHttp(
        auth: AuthInterceptor,
        hostSelection: HostSelectionInterceptor,
    ): OkHttpClient =
        OkHttpClient.Builder()
            .addInterceptor(hostSelection)
            .addInterceptor(auth)
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .build()

    /**
     * base URL 运行时可变:Retrofit 需要固定 baseUrl,这里用占位 host,
     * 真实地址由 OkHttp 拦截层(DynamicBaseUrlInterceptor)按 DataStore 重写。
     */
    @Provides
    @Singleton
    fun provideRetrofit(client: OkHttpClient, json: Json, session: SessionStore): Retrofit =
        Retrofit.Builder()
            .baseUrl(SessionStore.DEFAULT_BASE_URL)
            .client(client)
            .addConverterFactory(
                json.asConverterFactory("application/json".toMediaType())
            )
            .build()

    @Provides
    @Singleton
    fun provideMobileApi(retrofit: Retrofit): MobileApi =
        retrofit.create(MobileApi::class.java)

    /** Coil 与网络层共用 OkHttp(缓存/拦截一致)。 */
    @Provides
    @Singleton
    fun provideImageLoader(client: OkHttpClient): ImageLoader =
        ImageLoader.Builder(dev.jinsfoni.photobook.PhotoBookApp.instance)
            .components {
                add(OkHttpNetworkFetcherFactory(callFactory = { client }))
            }
            .build()
}
