# Fingerprint_JetBrains 账号半自动批量注册机

一键批量注册 JetBrains 账号，独立指纹浏览器 + 全流程自动化。你只需要手动点几下图片验证码，剩下的全部自动完成。

---

## 功能亮点

- 🎭 **独立指纹浏览器** — 每个窗口独立指纹（平台/品牌/时区/CPU），互不关联
- 📧 **自动申请临时邮箱** — 基于 nimail.cn，无需注册
- 🤖 **自动点击 "I'm not a robot"** — reCAPTCHA 复选框自动点击
- 👤 **你手动完成图片验证码**（唯一需要人工的步骤，无时间限制）
- 🔑 **自动接收验证码并填入** — 6位 OTP 逐位精准键入
- 📝 **自动填写密码和姓名** — 随机真人英文名，密码统一配置
- 🌏 **自动选择国家** — 默认日本，可在配置文件自由更改
- 💳 **自动弹出 Add credit card** — 注册完直接到信用卡填写界面
- 🚀 **支持多窗口并行注册** — 同时开多个浏览器，效率翻倍
- ⚙️ **所有参数可配置** — 密码、国家、并发数、超时时间等全部通过 `settings.json` 管理
- 💾 **注册结果永久保存** — 账号信息自动追加到文件，不会丢失

---

## 下载

点击上方绿色的 **Code** 按钮 → **Download ZIP** → 解压到任意位置即可。

---

## 使用前准备

| 需要准备 | 说明 | 下载地址 |
|---|---|---|
| **Python 3.10+** | 运行环境，安装时**必须勾选** "Add Python to PATH" | https://www.python.org/downloads/ |
| **指纹浏览器** | `chrome.exe`，放到脚本同目录或子目录下（见下方说明） | 自备 fingerprint-chromium |
| **梯子 / VPN** | 中国大陆用户需要，用来访问 Google 验证码和 JetBrains | — |

> Playwright 等 Python 依赖不需要单独下载，一条命令自动安装。

---

## 指纹浏览器放置

脚本会**自动搜索**目录下的指纹浏览器，可以使用默认的，也可以用你自己的，支持以下任意结构：

```
你的文件夹/
├── jb_register.py          ← 主脚本
├── settings.json            ← 配置文件（首次运行自动生成）
├── 浏览器文件
```

或者放在子目录中：

```
你的文件夹/
├── jb_register.py
├── settings.json
├── chromium/              
│   └── Application
        └──Chrome
```

支持的子目录名：`Chrome/Application/`，或任意两层以内的子目录。

也可以在 `settings.json` 中手动指定路径：
```json
{
    "browser": {
        "chrome_exe": "D:/my-browser/chrome.exe"
    }
}
```

---

## 快速开始

**1.** 解压下载的 ZIP 文件，把指纹浏览器的 `chrome.exe` 放进去

**2.** 打开文件夹，在地址栏输入 `cmd` 回车，打开命令行

**3.** 安装依赖（只需要第一次）：
```bash
pip install playwright
playwright install chromium
```

**4.** 启动程序：
```bash
python jb_register.py
```

**5.** 首次运行会自动生成 `settings.json` 配置文件 → 输入并发数量 → 按回车开始

**6.** 浏览器自动打开 → 自动填邮箱 → 自动点 reCAPTCHA → **你手动过图片验证码** → 后续全自动完成！

---

## 配置文件说明

首次运行自动生成 `settings.json`，所有参数都可以按需修改：

```json
{
    "password": "hajimi123",
    "country_code": "JP",
    "country_name": "Japan",
    "concurrent_count": 5,
    "final_url": "https://account.jetbrains.com/licenses/tokens",

    "email_provider": {
        "api_base": "https://www.nimail.cn",
        "domain": "nimail.cn",
        "username_length": 10
    },

    "browser": {
        "chrome_exe": "auto",
        "headless": false,
        "profile_root": "auto",
        "start_maximized": true
    },

    "registration": {
        "auto_select_country": true,
        "auto_click_add_credit_card": true,
        "accept_all_checkboxes": true
    },

    "fingerprint": {
        "platforms": [
            ["windows", "10.0.0"],
            ["windows", "11.0.0"],
            ["macos", "14.5.0"],
            ["macos", "15.2.0"],
            ["linux", null]
        ],
        "brands": [["Chrome", null], ["Edge", null], ["Opera", null], ["Vivaldi", null]],
        "timezones": [
            "Asia/Shanghai", "Asia/Tokyo", "Asia/Singapore",
            "America/Los_Angeles", "America/New_York",
            "Europe/London", "Europe/Berlin"
        ],
        "cpu_cores": [2, 4, 6, 8, 12, 16],
        "lang": "en-US"
    },

    "timeouts": {
        "email_wait_seconds": 240,
        "recaptcha_click_seconds": 25,
        "recaptcha_dialog_seconds": 300,
        "page_load_seconds": 60
    },

    "output_file": "jb_accounts.txt"
}
```

### 常用配置项

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `password` | 注册密码（所有账号统一） | `hajimi123` |
| `country_code` | 国家代码 | `JP`（日本） |
| `country_name` | 国家名称（用于 UI 选择） | `Japan` |
| `concurrent_count` | 默认并发窗口数 | `5` |
| `browser.chrome_exe` | 浏览器路径，`"auto"` 为自动搜索 | `auto` |
| `browser.profile_root` | 指纹数据存储位置，`"auto"` 为用户目录下 | `auto` |
| `registration.auto_select_country` | 是否自动选择国家 | `true` |
| `registration.auto_click_add_credit_card` | 是否自动点击 Add credit card | `true` |
| `timeouts.email_wait_seconds` | 等待验证邮件超时（秒） | `240` |
| `timeouts.recaptcha_dialog_seconds` | 等待人工过验证码超时（秒） | `300` |

> 💡 你只需要修改想改的字段，其余字段会自动使用默认值。JSON 中以 `_` 开头的键会被忽略，可以用来写注释。

---

## 注册流程（7步）

```
步骤1  自动申请临时邮箱（nimail.cn）
  ↓
步骤2  打开 JetBrains 注册页 → 自动填入邮箱 → 点击 Continue
  ↓
步骤3  自动点击 reCAPTCHA "I'm not a robot" 复选框
  ↓
步骤4  👤 你手动完成图片验证码（无时间限制）
  ↓
步骤5  自动检测验证完成 → 自动提交 → 自动接收邮件验证码 → 自动填入 OTP
  ↓
步骤6  自动填写姓名和密码 → 勾选协议 → 点击 Create account
  ↓
步骤7  自动跳转 tokens 页 → 自动选国家 → 自动弹出 Add credit card 对话框
```

---

## 注意事项

- 密码建议使用**英文字母和数字**的组合，避免特殊符号导致填写异常
- 注册成功后浏览器窗口**保持打开不关闭**，方便后续操作（如填写信用卡）
- CMD 窗口是后台进程，注册过程中**不要关闭**
- 如果验证码长时间加载不出来，检查**梯子是否正常**
- 每个浏览器窗口使用**独立指纹和独立数据目录**，互不影响
- 注册结果保存在 `jb_accounts.txt`，格式为 `邮箱 \t 密码 \t 姓名 \t 指纹种子`

---

## 项目结构

```
baiqi-GhostReg/
├── README.md                ← 你正在看的文件
├── jb_register.py           ← 主程序（单文件，开箱即用）
├── settings.json            ← 配置文件（首次运行自动生成）
├── chrome.exe               ← 指纹浏览器（你需要自己放进来）
└── jb_accounts.txt          ← 注册结果（自动生成）
```

---

## 技术栈

Python 3.10+ / Playwright / fingerprint-chromium / nimail.cn API

---

## 常见问题

**Q: 提示找不到 chrome.exe？**
> 把指纹浏览器的 `chrome.exe` 放到脚本同目录下，或在 `settings.json` 的 `browser.chrome_exe` 中填写完整路径。

**Q: reCAPTCHA 一直加载不出来？**
> 检查代理/VPN 是否正常。Google reCAPTCHA 在中国大陆无法直接访问。

**Q: 验证邮件一直收不到？**
> nimail.cn 偶尔会延迟，默认等待 240 秒。如果频繁超时，可以在 `settings.json` 中增大 `timeouts.email_wait_seconds`。

**Q: 注册成功但密码不对？**
> 检查 `settings.json` 中的 `password` 字段。密码在所有账号间共享。

**Q: 想换国家怎么办？**
> 修改 `settings.json` 中的 `country_code`（如 `US`、`KR`、`SG`）和 `country_name`（如 `United States`、`South Korea`、`Singapore`）。

**Q: 可以同时开几个窗口？**
> 运行时会提示输入数量，也可以在 `settings.json` 的 `concurrent_count` 中设置默认值。建议根据电脑性能选择 5-10 个。

---

## 免责声明

本项目仅供学习和研究自动化技术使用。使用者应遵守 JetBrains 的服务条款和相关法律法规。作者不对因使用本工具造成的任何后果承担责任。
