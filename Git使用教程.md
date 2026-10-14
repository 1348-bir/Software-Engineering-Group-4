# Git 使用教程

> 以本项目的实际操作流程为主线，从零开始讲清楚 Git 的常用操作。
> 适用对象：已经会用编辑器写代码、但还不熟悉 Git 命令行流程的同学。

---

## 目录

1. [Git 是什么](#1-git-是什么)
2. [安装与配置](#2-安装与配置)
3. [获取仓库：初始化 / 克隆](#3-获取仓库初始化--克隆)
4. [日常基本流程：改代码 → 提交](#4-日常基本流程改代码--提交)
5. [查看历史与回退](#5-查看历史与回退)
6. [分支操作](#6-分支操作)
7. [远程仓库：推送与同步](#7-远程仓库推送与同步)
8. [.gitignore 与误提交](#8-gitignore-与误提交)
9. [常见问题速查](#9-常见问题速查)
10. [本次项目实战复盘](#10-本次项目实战复盘)

---

## 1. Git 是什么

Git 是一个**分布式版本控制系统**，用来跟踪文件的历史变更、方便多人协作和备份代码。

核心概念（贯穿全文，先记住这四个）：

| 概念 | 含义 | 通俗理解 |
| --- | --- | --- |
| **工作区** | 你磁盘上看到的文件 | 你正在编辑的代码 |
| **暂存区（Index）** | `git add` 后进入的地方 | 打包间，挑好要发货的东西 |
| **本地仓库** | `git commit` 后存下的历史 | 装进你本地的仓库箱 |
| **远程仓库** | GitHub 上的仓库 | 网上的备份/协作中心 |

```text
工作区  --git add-->  暂存区  --git commit-->  本地仓库  --git push-->  远程仓库(GitHub)
```

---

## 2. 安装与配置

### 安装

Windows 推荐到 https://git-scm.com/downloads 下载安装包，一路 Next 即可。
安装后在任意终端输入 `git --version` 能输出版本号即安装成功。

### 首次配置（必须）

Git 每次提交都要记录"作者是谁"，用你的名字和邮箱：

```bash
git config --global user.name "你的GitHub用户名"
git config --global user.email "你的邮箱@example.com"
```

> `--global` 表示全局生效，只配一次。想只对当前仓库生效就删掉 `--global`。

查看当前配置：

```bash
git config --get user.name
git config --get user.email
```

---

## 3. 获取仓库：初始化 / 克隆

### 3.1 已有项目 → 初始化（本次项目就是这种方式）

```bash
cd 你的项目目录
git init          # 在目录里创建 .git 仓库
git status        # 查看当前状态：会看到一堆"未跟踪"的文件
```

### 3.2 别人的仓库 → 克隆下来

```bash
git clone https://github.com/用户名/仓库名.git
cd 仓库名
```

### 3.3 添加远程仓库（把本地仓库和 GitHub 仓库关联）

```bash
git remote add origin https://github.com/用户名/仓库名.git
git remote -v     # 查看已关联的远程仓库
```

> `origin` 只是远程仓库的**名字**（约定俗成叫 origin），换成别的名字也可以。

---

## 4. 日常基本流程：改代码 → 提交

一次正常的提交分三步：**改 → add → commit**。

### 4.1 查看状态

```bash
git status
```

- 红色 = 已修改/未跟踪（工作区有变化）
- 绿色 = 已暂存（add 过了，准备提交）

### 4.2 暂存（add）

```bash
git add main.py            # 只暂存这一个文件
git add templates/         # 暂存整个目录
git add .                  # 暂存所有变更（注意 .gitignore 会被尊重）
```

### 4.3 提交（commit）

```bash
git commit -m "本次改动说明"
```

> 提交信息建议写清楚"改了什么、为什么改"，而不是"改了代码"。用中文或英文都可以。

### 4.4 查看历史

```bash
git log --oneline          # 简洁版历史
git log --oneline -5       # 只看最近 5 条
```

### 完整流程图

```bash
# 例：本次项目中新增"GitHub 仓库统计"功能后的提交过程
git add main.py templates/github_counter.html templates/projects.html
git commit -m "feat: 新增 GitHub 仓库链接代码统计功能"
```

---

## 5. 查看历史与回退

### 5.1 看看改了什么

```bash
git diff                    # 工作区 vs 暂存区（还没 add 的改动）
git diff --cached           # 暂存区 vs 上一次提交（add 了但没 commit 的改动）
```

### 5.2 撤回：还没提交怎么办

| 情况 | 命令 | 效果 |
| --- | --- | --- |
| 改乱了，想放弃工作区改动 | `git restore 文件` | 回到上一次提交的状态 |
| 不想暂存某个文件了 | `git restore --staged 文件` | 从暂存区移出，文件内容不变 |
| 提交信息写错了 | `git commit --amend -m "新信息"` | 修改最近一次提交的说明 |
| 想回退到某个历史提交 | `git reset --hard 提交号` | 危险！会丢弃之后的改动，谨慎使用 |

> `git reset --hard` 会丢代码，非必要不用。实在要用之前先 `git stash` 或备份。

---

## 6. 分支操作

分支 = 一条独立的开发线，互不干扰，开发完再合并。

```bash
git branch                    # 列出本地分支，* 表示当前分支
git branch dev                # 新建分支 dev
git checkout dev              # 切换到 dev（新版也可用 git switch dev）
git checkout -b dev           # 新建并切换，一步到位
git merge dev                 # 把 dev 合并到当前分支
git branch -d dev             # 删除已合并的分支
```

**建议工作流：**

```bash
git checkout -b feature-xxx   # 新功能开一个分支
# ...写代码、add、commit...
git checkout master           # 回到主分支
git merge feature-xxx         # 合并
```

---

## 7. 远程仓库：推送与同步

### 7.1 首次推送

```bash
git push -u origin master
```

- `-u` = `--set-upstream`，把本地 `master` 和远程 `origin/master` 建立追踪关系，以后直接 `git push` 即可
- 分支名注意：新仓库默认可能是 `main`，老仓库是 `master`，以你本地实际分支为准

### 7.2 日常推送

```bash
git push                      # 推送当前分支
git push origin master        # 明确推送到指定远程和分支
```

### 7.3 拉取更新

```bash
git pull                      # 拉取远程并自动合并到当前分支
git fetch origin              # 只拉取到本地记录，不合并（先看看再决定）
```

### 7.4 推送被拒绝怎么办

远程仓库有了本地没有的提交（比如 GitHub 网页端生成了 README），直接 push 会被拒绝：

```bash
git pull --rebase origin master   # 先把远程改动"垫"到本地提交下面
git push                          # 再推
```

> 涉及多人协作或不确定时，先 `git fetch` + `git log` 看清楚再操作，不要无脑 `--force`。

---

## 8. .gitignore 与误提交

### 8.1 作用

`.gitignore` 告诉 Git **哪些文件不要跟踪**。适合放：虚拟环境、编译产物、数据库、密钥、大数据文件。

本项目 `.gitignore` 的一部分：

```gitignore
.venv/              # 虚拟环境
__pycache__/        # Python 缓存
*.db                # 运行时生成的数据库
test/               # 测试数据
*.zip               # 压缩包
```

### 8.2 已经误提交了怎么移除（本次项目的实战场景）

项目中 `test/` 和 `test.zip` 曾被误暂存，但没有提交。正确移除方式是**只从暂存区/仓库移除，不删磁盘文件**：

```bash
git rm --cached -r test          # 把 test/ 从暂存区移除
git rm --cached test.zip         # 同上
# 然后再把这些规则写进 .gitignore，防止下次 git add . 又加回来
```

> 一定要加 `--cached`：表示"从仓库索引里移除"，磁盘文件原封不动。
> 不加 `--cached` 的 `git rm` 会连磁盘文件一起删掉！

### 8.3 修改 .gitignore 后

```bash
git add .gitignore
git commit -m "chore: 更新忽略规则"
```

---

## 9. 常见问题速查

| 问题 | 原因 | 解决 |
| --- | --- | --- |
| `git push` 一直提示输入密码 | 用 HTTPS 推送需要认证 | 配合 Git Credential Manager 登录一次即可；或改用 SSH |
| 推送显示 `Everything up-to-date` | 本地没有新提交 | 先 `git status` 确认有没有 `git add` / `git commit` |
| `git add .` 后大文件/测试数据进仓库了 | 没有忽略规则 | 用 `git rm --cached` 移除 + 更新 `.gitignore` |
| 推不上，报 `non-fast-forward` | 远程有新提交 | `git pull --rebase` 后再推 |
| 提交作者不是我 | 没配 user.name/email | 见 [第 2 节](#2-安装与配置) |
| 不小心 commit 了敏感信息 | 提交里含密码/token | 尽快改密；用 `git filter-branch` 或 BFG 清理历史（谨慎） |

---

## 10. 本次项目实战复盘

下面完整还原本次"个人主页项目"从本地到 GitHub 的全部过程：

```bash
# 1. 配置（如果还没配过）
git config --global user.name "wenjingxiong"
git config --global user.email "1317463321@qq.com"

# 2. 查看仓库状态：还没有任何提交，且暂存区里混入了测试数据
git status

# 3. 把误暂存的测试数据移出（文件保留在磁盘）
git rm --cached -r test
git rm --cached test.zip

# 4. 更新 .gitignore，补上 *.zip 规则
#    （编辑 .gitignore 文件）

# 5. 暂存所有项目文件并确认
git add .
git status --short          # 只看到 22 个项目文件，干净了

# 6. 创建初始提交
git commit -m "init: Flask personal website (code stats / math practice / 24 game / GitHub repo stats)"

# 7. 关联远程仓库并推送
git remote add origin https://github.com/wenjingxiong/personal-website.git
git push -u origin master

# 8. 验证
git status -sb              # 输出 ## master...origin/master，无 ahead/behind
git ls-remote origin        # 远程 master 指向的 commit 与本地一致
```

### 以后的日常

```bash
# 每改完一批代码：
git status                  # 看改了什么
git add .                   # 暂存
git commit -m "你的改动说明" # 提交
git push                    # 推到 GitHub
```

---

*文档完 · 项目仓库：https://github.com/wenjingxiong/personal-website*
