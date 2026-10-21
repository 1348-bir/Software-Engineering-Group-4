# 软件工程第四小组 · Group 04 Studio

徐敬轩、文敬雄的小组成员主页，整合原仓库的数学练习、24 点、骰子游戏与 PersonalCodeStudio 的主页设计、多语言代码统计和网址导入。

## 快速运行

需要 Python 3.10 或更高版本。Windows 双击 `start.bat`，等待依赖安装，然后访问 **http://127.0.0.1:5050**，保持窗口打开。按 Ctrl+C 停止服务。

在 PyCharm 中打开本仓库，解释器选择 `.venv/Scripts/python.exe`，运行 `app.py` 或 `main.py`。两者启动同一个融合后的应用。

手动运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

macOS / Linux：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

端口占用时先设置 `PORT` 环境变量。服务默认仅本机访问；发布到互联网时需要另外配置正式 WSGI 服务、固定 `SECRET_KEY`、HTTPS 与访问控制。上传 GitHub 仓库不会自动部署网站。

## 功能与入口

| 入口 | 功能 |
| --- | --- |
| `/` | 小组首页，徐敬轩与文敬雄的成员卡片 |
| `/members` | 成员列表、各成员介绍和独立头像上传 |
| `/projects` | 全部小组项目入口 |
| `/code-stats` | 文件、文件夹、ZIP、源码网址与公开 GitHub 仓库统计、搜索及 CSV 导出 |
| `/math` | 数学工具总览 |
| `/math/` | 原仓库的可定制数学出题、自动批改、会话历史 |
| `/math/print` | 练习卷 / 答案卷打印，支持题数、列数与行距 |
| `/math/upload` | 图片算式识别入口，依赖可选 OCR 环境 |
| `/game24/` | 原仓库的 24 点多解练习与逐次历史 |
| `/dice/` | 原仓库的双骰游戏，总和 7 获胜，保存会话记录 |
| `/arithmetic` | 10 题快速算术挑战、计时与逐题解析 |
| `/game24` | 24 点快速挑战，参考答案与一次性成绩记录 |
| `/history` | 快速挑战记录及其他模块历史入口 |

注意 `/math` 是总览，`/math/` 是定制练习；`/game24` 是快速挑战，`/game24/` 是多解练习。导航链接已按对应功能配置。

原来的 `/profile`、`/projects/code-counter`、`/projects/github-counter` 链接仍能访问；旧统计表单 POST 也接入新的统计引擎。文敬雄原有详细档案保留在其成员页面的链接中。

## 成员资料与头像

编辑 `team.json` 修改小组名称、介绍、两位成员的技能和关注方向。头像在成员详情页分别上传，限制 3 MB，保存到 `static/uploads/`。头像和运行记录不提交 Git。成员页是资料展示，不是登录账号；定制练习与游戏记录按浏览器会话隔离，快速挑战成绩保存在本地公共历史库。

## 代码统计与网址导入

- 单文件、上传合计、网址下载及解压后总量均限制为 **1 GB = 1024³ 字节**，最多 1000 个文件；请求额外预留 4 MB 表单开销。忽略 Git、虚拟环境、node_modules 等目录。
- 使用 Pygments 识别多种语言，统计物理总行数、代码行、纯注释行、空行和含注释行。代码与行尾注释同行时计为代码行，同时计入含注释行；Python 文档字符串与 C/C++ 预处理指令计为代码。
- 语言汇总表按课程图片提供：语言、源文件数、代码行数、空行数、注释行数、函数个数、最大值、最小值、均值、中位数。固定显示 C、C++、Java、Python、C#，其他语言有文件时追加行。
- 后四项按**每个函数的有效代码行数**计算，包含定义行、Python 装饰器和有内容的括号行，不含空行与纯注释行。Python 用 AST，C/C++/Java/C# 用 Tree-sitter 识别带函数体的定义；计入类方法、构造函数与 C# 局部函数，不计单独声明、调用和匿名 lambda。嵌套函数分别计数，外层长度包含嵌套部分。跨文件合并全部函数长度后再计算均值和中位数，不平均文件均值。
- 没有函数时函数数为 0、长度指标为“—”；未支持函数分析的语言保留行数统计，函数列为“—”。语法不完整会列出文件，并用 * 标记可能不完整的汇总；不把解析失败伪装成准确的零函数。CSV 同时包含语言汇总表和文件明细。
- 网址支持公开 GitHub 仓库首页、单文件 blob 链接、源码直链和 ZIP。普通网页仅取得返回的 HTML，不能取得服务器后端代码；暂不支持需要登录、验证码的地址与 GitHub 子目录。
- 仅连接公开互联网地址的标准 HTTP/HTTPS 端口，逐次校验重定向并固定已验证 IP；不读取本机或内网地址。下载写入临时文件，处理后关闭，不执行上传源码。
- 保留准确词法分析需要内存中的完整解码文本，接近 1 GB 的单文件可能需要数 GB 内存并耗时较长。已验证大小配置、边界及超过旧 24 MB 限制的真实上传，未做完整 1 GB 单文件性能测试。

## 可选 OCR 与题库

基础功能只依赖 `requirements.txt`。图片识别沿用原仓库的 PaddleOCR 适配；未安装兼容的 PaddleOCR/PaddlePaddle 环境时会提示识别不可用，其他功能正常。不同 Python 版本的 OCR 包兼容性不同，不作为默认依赖。

不在每次启动时生成一万题，避免启动等待；普通练习会按需补题。原来的 `/math/api/generate` 题库生成接口保留。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

融合后的 64 项测试涵盖五语言函数统计、函数长度聚合、双方功能、成员页、头像隔离、旧入口、定制题批改、骰子及历史隔离。浏览器检查先启动网站，再运行：

```powershell
$env:SKIP_REMOTE_QA = '1'  # 离线检查，不重复外网下载
.\.venv\Scripts\python.exe tools\verify_edge.py
```

需要本机 Microsoft Edge。截图保存到 `previews/`，该目录不提交。可用 `STUDIO_URL` 指定非默认端口。

## 融合说明

以原仓库提交 `412a5a8` 为基础保留 `math_practice/`、`game_24/`、`dice_game/` 及其页面、算法和数据结构，接入统一 Flask 应用。旧代码统计实现合并为 Pygments 引擎；保留已有 URL。`main.py` 与 `app.py` 使用同一入口，主页改为小组展示，双方原项目的本地数据未复制或上传。
