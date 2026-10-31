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

**debug 包名带 `.debug` 后缀**(`dev.jinsfoni.photobook.debug`,release 不变)。2026-10-31
实机事故:手机上先装了本地 build 的 debug 签名包(包名同为 `dev.jinsfoni.photobook`),
之后官方 release 用的是正式密钥,两种装法都被 `INSTALL_FAILED_UPDATE_INCOMPATIBLE`
挡住(手机提示「已安装签名冲突的应用」),只能卸载重装。加后缀后开发包与正式版可以
同时存在,互不干扰;本地 `assembleRelease` 在缺 `app/release.keystore` 时仍会回落
debug 签名 —— 那种包**不要**装到已装正式版的机器上。

## 服务端地址

默认 `DEFAULT_BASE_URL`(data/remote/MobileApi.kt)。真机调试:改为局域网地址(如 `http://192.168.x.x:8000/api/mobile/`),或等 M3 S9 多服务器设置页。服务端启动:`uvicorn app.main:app`(见仓库根 README)。

## 发版

GitHub Release **published** 时自动构建(见 `.github/workflows/android-release.yml`):
跑单测 → assembleRelease → **`app/release.keystore`(CI 从 `ANDROID_KEYSTORE_BASE64`
等 Secrets 解出)签名** → APK(`PhotoBook-<tag>.apk`)上传到该 Release 资产。
Secrets 未配置时回落 debug 签名(会打 warning,那种产物不能覆盖安装正式版)。

**签名方案必须 v1+v2+v3 全开**(`signingConfigs` 里显式 `enableV1Signing/V2/V3`),
不能靠 AGP 默认值。2026-11-01 实机事故:AGP 在 `minSdk >= 24` 时默认只做 v2 签名,
APK 里没有 `META-INF/MANIFEST.MF + CERT.SF + CERT.RSA`,v1.9.10 装到 OPPO PKT110
(ColorOS / API 36)直接报「解析失败:安装包没有签名文件」,装不进去。显式全开后
`apksigner verify -v --min-sdk-version 21` 才能看到 `v1/v2/v3: true`
(注意:带 v3 的包在默认参数下 apksigner 只校验最高一档,v1/v2 会显示 false,
那是「跳过校验」不是「签名坏了」)。

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
