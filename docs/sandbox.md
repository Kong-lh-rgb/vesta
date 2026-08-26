# Vesta Sandbox V1

Sandbox V1 保护能够执行任意代码的入口，不改变 AgentRuntime 的 `ToolCall → ToolResult`
协议。权限审批回答“是否允许做”，Sandbox 回答“获准后最多能影响哪里”。

## 当前覆盖范围

- `run_shell_command`：workspace 可读写，网络默认拒绝；
- 第三方 stdio MCP Server：macOS Seatbelt 隔离整个子进程树；
- MCP 环境变量：只继承 `HOME`、语言、`PATH`、证书和临时目录等运行必需项，配置中的
  `${ENV_NAME}` 按需注入；
- `.git`、`.vesta`、`.env` 等控制边界和敏感文件在 workspace 内继续拒绝读取或写入；
- 沙箱不可用、路径无效或策略无法强制时 fail closed。

受控的内置文件、Task、Memory、Artifact 和 Search 工具继续在 Host 中执行，它们通过窄接口
和领域校验限制能力。Computer Runtime 必须操作真实 macOS 桌面，继续依赖审批、ComputerSession、
exact target、fresh observation 和执行后验证。

## 执行链

```text
ToolCall
  ↓
Permission / Approval
  ↓
ShellCommandTool 或 StdioMCPClient
  ↓
SandboxSupervisor
  ├─ 解析 executable 与工作目录
  ├─ 编译读写根、敏感路径和网络策略
  ├─ 清理环境变量
  └─ 选择平台 Backend
        ↓
macOS Seatbelt → 子进程树
```

MCP 默认配置：

```json
{
  "sandbox": {
    "filesystem": "workspace_write",
    "network": "unrestricted",
    "readable_roots": [],
    "writable_roots": [],
    "allowed_domains": []
  }
}
```

`filesystem` 支持：

- `none`：不暴露 workspace；
- `read_only`：workspace 只读；
- `workspace_write`：workspace 可读写，默认值；
- `host`：显式关闭 OS 隔离，仅供用户确认过的可信进程使用。

`network` 当前支持 `denied` 和 `unrestricted`。`allowed_domains` 已进入稳定配置模型，但在域名
代理完成前不能被 macOS 后端可靠强制；配置非空时拒绝启动，避免把白名单请求弱化成全网访问。

## 运行时兼容根

Seatbelt 在 deny-by-default 下仍需读取系统运行库、可执行文件和包管理器缓存。Vesta 仅为检测到的
运行时开放必要目录，例如 Homebrew、npm cache、uv cache 与 uv tool directory，不开放整个用户
主目录。uv/npm 的缓存写权限用于现有 `uvx` / `npx` MCP 启动兼容，不代表这些进程可以访问 SSH、
浏览器或 Keychain 数据。

## 尚未实现

- Linux Bubblewrap/Landlock 后端；
- Docker/Podman 严格隔离后端；
- 基于代理的域名 allowlist；
- CPU、内存、磁盘与进程数量限制；
- Skill 脚本的独立执行入口；
- 每个 MCP Server 独立的包缓存目录。

V1 在非 macOS 平台对原生隔离请求 fail closed。未来执行后端可以替换，但上层 Policy、MCP、
ToolResult、Approval 和 Trace 语义保持不变。
