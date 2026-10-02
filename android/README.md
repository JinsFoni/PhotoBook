# PhotoBook Android

PhotoBook 自托管写真库的 Android 客户端(Compose)。服务端见仓库根目录(FastAPI)。

## 当前状态

**M0 骨架 + M1 主链路**(android 分支):

- S8 登录 → S1 发现 → S2 写真列表 → S3 详情 → S4 灯箱(缩放/收藏/下载)
- 架构与设计文档:`docs/android-architecture.md`、`docs/android-design/design.md`
- 实施计划与偏差记录:`docs/superpowers/plans/2026-10-03-android-m0-m1.md`、`docs/android-architecture.md` §11

## 构建

要求:JDK 17,Android SDK(minSdk 31,targetSdk 36)。

```bash
cd android
./gradlew :app:assembleDebug        # APK: app/build/outputs/apk/debug/
./gradlew :app:testDebugUnitTest    # 单元测试(19 项)
```

注意:工程启用 `android.builtInKotlin=false` + `android.newDsl=false`(Gradle 9.6 + AGP 兼容配置),buildscript classpath 钉 KGP 2.4.20;不要在 android{} 块外配 testOptions。

## 服务端地址

默认 `DEFAULT_BASE_URL`(data/remote/MobileApi.kt)。真机调试:改为局域网地址(如 `http://192.168.x.x:8000/api/mobile/`),或等 M3 S9 多服务器设置页。服务端启动:`uvicorn app.main:app`(见仓库根 README)。

## 测试账号

`demo / demo123`(服务端种子数据)。

## 结构

```
app/src/main/java/dev/jinsfoni/photobook/
├── core/design/        # PhotoTheme 三主题 + 字体/色板 token
├── data/
│   ├── prefs/          # SessionStore(DataStore Preferences)
│   ├── remote/         # Retrofit MobileApi + DTO + ApiErrors + MediaUrls
│   └── repo/           # Collections/Favorites/Auth 仓库
├── di/                 # Hilt 模块
├── ui/
│   ├── components/     # TagChip/Skeleton/EmptyState 等无涟漪组件
│   ├── icons/          # 手绘 StrokeIcon(Path 状态机)
│   ├── nav/            # AppRoot 导航 + GlassTabBar(haze 玻璃)
│   └── screens/        # login/explore/collections/detail/lightbox
└── MainActivity.kt
```
