# AI4Papers 每轮改动、同步与发布流程

本文档描述每轮代码改动完成后，从维护上传清单到服务器构建和服务重载的标准流程。

## 1. 维护改动文件清单

将本轮所有需要同步的文件绝对路径加入根目录的 `changed_files_abs_paths.txt`，每行一个路径并去重。例如：

```text
D:\Datas\Programming\Cursor\AI4Paper02\ArxivPaper4\View\src\components\PaperChat.vue
```

清单可以包含源代码、测试、配置和有意维护的静态资源，但禁止加入：

- `%USERPROFILE%\.ssh` 下的私钥或公钥；
- `.env`、API Key、密码或其他凭据；
- `node_modules`、`test-results`、运行数据和生成的构建目录；
- 与本轮任务无关的文件。

清单必须包含本轮新增的流程脚本或文档本身，以确保服务器副本同步更新。

## 2. 本地验证

根据改动范围运行对应检查。网页端至少运行：

```powershell
cd View
npm run typecheck
npm test
npm run build
```

涉及后端时运行：

```powershell
python -m unittest discover -s Sever/tests -p "test_*.py"
```

提交前运行：

```powershell
git diff --check
```

只有验证通过的改动才允许同步和发布。

## 3. 提交 Git

只暂存本轮任务涉及的文件，检查暂存差异后创建范围明确的提交。不要把工作区中其他人的改动、生成目录或凭据一起提交。

部署脚本会检查 `changed_files_abs_paths.txt` 中的每一个文件。只要其中任意文件仍处于已修改、已删除或未跟踪状态，部署（包括 `-DryRun`）都会立即停止。这样可以避免上传工作区中的半成品或其他人的未提交修改。工作区中不在清单内的改动不会阻止发布。

## 4. 判断发布目标和 npm install

发布目标：

- `View`：网页端；
- `Mobile`：`mobile_new` 移动端；
- `Both`：两个前端都需要构建；
- `Backend`：只同步后端并重启服务，不构建前端。

仅当本轮修改了目标客户端的 `package.json`、锁文件，或服务器依赖尚未安装时，才添加 `-InstallNpm`。普通源码修改不要重复执行 `npm install`。

当前生产服务器只有约 1.8 GiB 内存且没有 Swap，Vite/Rollup 可能在服务器构建时被 OOM 终止。因此当前服务器默认使用本地已验证的 `dist` 发布模式 `-UseLocalDist`。该模式不会把 `dist` 加入 Git 或永久改动文件清单，而是临时打包、上传并原子替换服务器产物。

## 5. 一条命令上传并发布

网页端且需要安装依赖：

```powershell
.\deploy_changed_files.ps1 -Target View -InstallNpm
```

网页端且无需安装依赖：

```powershell
.\deploy_changed_files.ps1 -Target View
```

当前低内存服务器推荐的网页发布方式：

```powershell
cd View
npm run build
cd ..
.\deploy_changed_files.ps1 -Target View -UseLocalDist
```

移动端对应使用：

```powershell
.\deploy_changed_files.ps1 -Target Mobile -InstallNpm
.\deploy_changed_files.ps1 -Target Mobile
```

移动端低内存发布对应使用：

```powershell
cd mobile_new
npm run build
cd ..
.\deploy_changed_files.ps1 -Target Mobile -UseLocalDist
```

两个客户端都需要构建：

```powershell
.\deploy_changed_files.ps1 -Target Both
```

后端单独发布：

```powershell
.\deploy_changed_files.ps1 -Target Backend
```

如需检查计划但不执行上传或发布：

```powershell
.\deploy_changed_files.ps1 -Target View -InstallNpm -DryRun
```

## 6. 脚本在服务器上的动作

`deploy_changed_files.ps1` 会先调用 `upload_changed_files.ps1`，通过专用私钥无密码上传清单中的文件。随后服务器脚本会：

1. 进入 `/projects/ArxivPaper4/View` 或 `/projects/ArxivPaper4/mobile_new`；
2. 按需执行 `npm install`；
3. 为 Vite 和 TypeScript 命令补齐执行权限；
4. 执行 `npm run build`；
5. 检查并列出 `dist`；
6. 执行 `systemctl restart arxiv-api`；
7. 先执行 `nginx -t`，通过后再执行 `systemctl reload nginx`；
8. 确认 `arxiv-api` 和 `nginx` 都处于 active 状态。

使用 `-UseLocalDist` 时，第 1-5 步替换为：检查本地 `dist/index.html`、临时打包、上传到服务器 `.deploy` 目录、解压校验，并通过备份目录原子替换现有 `dist`。替换失败会恢复旧产物。

成功标志为：

```text
DEPLOY_OK target=... install_npm=...
Deployment completed successfully.
```

## 7. 密钥和安全要求

同步专用私钥固定保存在仓库外：

```text
C:\Users\Liu Lin\.ssh\ai4papers_sync_ed25519
```

不得读取、展示、提交或上传私钥内容。`sf_llin` 属于另一台服务器，不得用于 AI4Papers 服务器。
