# Code Review Agent — 自动代码评审 Agent

基于 tRPC-Agent-Python 框架构建的自动代码评审 Agent，集成 Skills、沙箱执行、数据库存储、Filter 治理和监控审计能力，可对 git diff 进行自动化审查并输出结构化报告。

## 环境要求

- Python >= 3.10
- 依赖：见 `requirements.txt` 或 `pyproject.toml`

## 安装

```bash
# 从项目根目录安装
pip install -e .

# 或直接运行（依赖已安装的情况下）
cd examples/skills_code_review_agent
```

## 快速开始

### 使用测试样本运行（dry-run 模式，无需 API Key）

```bash
cd examples/skills_code_review_agent

# 运行无问题样本
python dry_run.py --fixture 01_clean

# 运行安全漏洞样本
python dry_run.py --fixture 02_security_leak

# 运行全部 8 条样本
for f in 01 02 03 04 05 06 07 08; do
    python dry_run.py --fixture "${f}_clean"
done
```

### 审查本地 diff 文件

```bash
python review_agent.py --diff-file /path/to/changes.diff
```

### 审查 git 工作区变更

```bash
python review_agent.py --repo-path /path/to/repo
```

### 列出可用样本

```bash
python review_agent.py --list-fixtures
```

## 输出

- `review_report.json` — 结构化 JSON 报告
- `review_report.md` — 可读 Markdown 报告

## 测试样本

| 样本 | 场景 | 预期 |
|------|------|------|
| `01_clean.py.diff` | 无问题代码 | 空 findings |
| `02_security_leak.py.diff` | 硬编码密钥/密码 | severity=high |
| `03_async_resource_leak.py.diff` | 未关闭 aiohttp ClientSession | 资源泄漏 |
| `04_db_connection_leak.py.diff` | 数据库连接未释放 | 连接泄漏 |
| `05_test_missing.py.diff` | 新增函数无测试 | warning |
| `06_duplicate_finding.py.diff` | 同一问题重复出现 | 去重后只报 1 条 |
| `07_sandbox_failure.py.diff` | 沙箱执行超时/失败 | 任务不崩溃 |
| `08_secret_masking.py.diff` | 多种敏感信息 | 全部脱敏 |

## 项目结构

```
examples/skills_code_review_agent/
├── review_agent.py          # 主入口
├── dry_run.py               # 干跑模式
├── config.py                # 配置管理
├── cli.py                   # CLI 参数解析
├── models.py                # 数据模型
├── diff_parser.py           # diff 解析器
├── sandbox.py               # 沙箱执行器
├── secret_masker.py         # 敏感信息脱敏
├── filters.py               # Filter 治理
├── filter_chain.py          # Filter 编排链
├── deduper.py               # 去重降噪
├── report_generator.py      # 报告生成
├── monitor.py               # 监控审计
├── db/                      # 数据库层
│   ├── schema.sql
│   ├── storage.py
│   └── init_db.py
├── skills/code-review/      # CR Skill
│   ├── SKILL.md
│   ├── rules/               # 规则文档
│   └── scripts/             # 沙箱脚本
└── fixtures/                # 测试样本
    ├── 01_clean.py.diff
    └── ...
```