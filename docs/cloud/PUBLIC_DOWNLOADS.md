# 安康安卓官网下载页

更新日期：2026-10-14。公网云服务0.1.5、数据库schema1；这次增加公开下载入口，不升级0.2.0工作台或迁移患者数据。

## 对外入口

- [官网下载页](https://139.224.216.18/download)：无需账号，手机/电脑都可访问。
- [默认安卓下载](https://139.224.216.18/download/android)：用户选择的最新手机功能版0.4.1，versionCode41，Android最低API29（Android10）。
- [现有云账号兼容版](https://139.224.216.18/download/android/0.3.1)：原0.3.1保留；较高versionCode不能直接降级安装，不建议卸载或清数据。
- 技术人员微信：AK2452409。页面支持点击复制；浏览器不允许复制时选中微信号，并提示手动复制。

网站顶部保留网页版（`/account?next=/`）与医生端（`/care`），底部保留云端档案（`/account`）。账号登录表单增加“下载App”链接；现有已登录首页、`/capture`、医生网页和身份边界不改。公网根入口`/`仍是原用户应用，不替换成下载页。

0.4.1来自原E已生成的安装包，不是此次重构建。它的新医患工作台需要0.2.0/schema2后端，当前公网仍是0.1.5/schema1，因此下载页有简短兼容说明；发布安装包不意味着新版工作台已接公网。此次未进行红米真机安装、原生登录/医患消息/计划采用验收。

## 安装包来源

源文件为原E仓库`android_offline/dist/tele-rehabilitation-mobile-0.4.1.apk`：21,652,734字节，SHA256 `482A9509290F9E0914D81A04CD0243DAB909BA82BA1EFF81A53AF98C31961D50`。通过aapt读取实际包名`cn.tele.rehabilitation.offline`、versionName0.4.1、versionCode41、minSdk29，并用原工具验证v3签名。签名证书SHA256 `607edd7dc1df261e52fa2fe35ea6391e1ce77cbcebc315fea80dd815bac1a5d8`，保持原证书；这不代表应用商店审核或真机验收。

服务器将其保存为`cloud_service/static/ankang-0.4.1.apk`，公开浏览器实际下载后的字节与上述SHA一致。原0.3.0/0.3.1包及0.3.1manifest保留，0.3.1原SHA `DAE4918F8078A9D80ED7596808FE94122D6491D54DB4892C0AC0155B06923B08`不变。APK不提交Git；公开元数据在`cloud_service/static/android-downloads.json`，不是患者资料。

## 实现与维护

`cloud_service/downloads.py`在现有服务中注册`/download`、`/download/android`、`/download/android/{version}`、`/download/releases.json`。仅允许清单中的固定版本及`ankang-<version>.apk`文件名，解析后的文件必须仍在指定目录中；启动时核对大小和SHA，下载时核对文件状态。未知版本404，丢失/改动安装包503，不接受查询参数提供路径，不公开内部磁盘路径。下载是attachment，明确APK MIME，支持HEAD/Range。

下载页独立HTML/CSS/JS，使用原安康图标、微软雅黑优先字体及绿色/白色基调；frontend-design规范用于保持简洁层级和触屏按钮，不重做正式产品界面。没有第三方脚本、追踪器或新增患者缓存；页面保持严格self CSP，不为复制功能放宽inline脚本。

更新安装包时先保留旧文件，核对新包实际版本、原签名、大小和SHA，再更新清单及部署。清单默认版本与下载按钮由同一配置产生；不能只把旧文件改名冒充新版本。后端本轮下载处理不访问患者数据库，不创建账号或改医嘱。

当前`/opt/ankang-cloud/current`指向`releases/0.1.5`；旧0.1.4保留，回退只切代码链接并重启同一服务，不恢复旧数据库。部署前加密备份已成功。详细证据见[本轮下载页验收](../validation/PUBLIC_DOWNLOADS_2026-10-14.md)。
