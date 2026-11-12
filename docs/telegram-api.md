# 获取 Telegram API ID 和 API Hash

拾刻 Web 面板和 `telethon` 脚本入门版都需要这两项。它们来自 Telegram 官方的应用申请页面，和通知机器人的 Bot Token 是不同的东西。

## 1. 登录 Telegram 官方网站

打开 [my.telegram.org/apps](https://my.telegram.org/apps)，使用已经注册 Telegram 的手机号登录，带上国家区号，例如 `+86…`。

**这个网站的登录验证码通过 Telegram 发到已登录设备，不是短信。** 打开手机或桌面 Telegram 的服务消息查看，详见[官方登录页](https://my.telegram.org/auth)。

登录后选择 **API development tools**。

## 2. 创建应用

首次使用会看到 **Create new application**，可以参考：

| 字段 | 示例 |
| --- | --- |
| App title | `Shike Tasks` |
| Short name | `shiketasks`，5–32 位英文字母和数字，不加空格或下划线 |
| URL | 自己的 GitHub 主页，例如 `https://github.com/你的用户名` |
| Platform | `Desktop` |
| Description | `Personal Telegram task automation` |

点击 **Create application**。如果已经看到 **App configuration**，直接用原有信息，无需重新创建。[Telegram 官方说明](https://core.telegram.org/api/obtaining_api_id)指出，一个手机号目前只能关联一个 `api_id`。

## 3. 保存并填写

在应用配置页找到 **App api_id** 和 **App api_hash**。下面只演示格式：

```text
api_id:   12345678
api_hash: 0123456789abcdef0123456789abcdef
```

- **Web 面板**：部署并用管理密码登录后，在首次引导或“设置 → Telegram 连接”中填入，再扫码接入账号。无需先手动生成 StringSession。
- **Actions 脚本**：按[入门版说明](../README.actions.md)生成各账号的 StringSession，并配置 `TELEGRAM_API_ID`、`TELEGRAM_API_HASH` 和 `TELEGRAM_ACCOUNTS_JSON`。

API 信息本身不代表已经登录了 Telegram；仍需通过扫码或验证码完成账号授权。

## 几种密码和凭证的区别

| 信息 | 来源 | 用途 |
| --- | --- | --- |
| 拾刻管理密码 | 部署时自己在终端设置 | 登录自己的网页面板 |
| API ID / API Hash | `my.telegram.org` | 连接 Telegram API |
| Telegram 登录验证码、两步验证密码 | 你的 Telegram 账号 | 授权拾刻登录该账号 |
| StringSession | 账号授权后生成 | 保存账号登录会话；Actions 使用，Web 可选导入 |
| Bot Token | 自己创建的通知机器人，可选 | 使用独立机器人发送通知 |

请把 API Hash 和会话信息保存在自己的可信位置，不要放进公开截图、仓库或 Issue。StringSession 能代表你的账号操作；怀疑泄露时，在 Telegram“设置 → 设备”中终止对应会话。

## 常见问题

- **找不到验证码**：检查填的手机号及国家区号，去已登录 Telegram 设备的服务消息里找。
- **创建应用报错**：先检查 Short name 和其他字段；已有应用时使用原来的信息。遇到限制先等候，不要反复提交。
- **API ID / Hash 无效**：分别填写，不要把字段名、冒号、引号或空格一起粘贴。
- **网页能打开，拾刻连接超时**：访问申请网站和后端连接 Telegram 是两条网络路径。部署机器或容器仍需能访问 Telegram，可在面板设置服务器可用的代理。
