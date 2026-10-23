# Updating Marginalia · 更新学习资料库

The updater imports original files into course folders and rebuilds the website catalog, the repository index, and each course index. English remains the default website language; Chinese filenames are preserved. Files are copied, so the original source files stay in place.

## Quick start on Windows

1. Open your local clone of this repository and double-click **更新资料库.cmd**.
2. Choose **添加资料**, select an existing course or **新建课程**, then select a category.
3. Select multiple files in the file picker, or choose a folder.
4. Review the list and choose **上传并更新网站**. The tool commits and pushes the update, then checks the published catalog.

Choose **仅保存到本地，稍后上传** to prepare files offline. Later, launch the tool again and choose **上传之前已保存的更新**.

## Requirements

- Python 3.11 or newer. The Windows launcher also detects the bundled Codex Python runtime on this computer.
- `pypdf`, pinned in [`scripts/requirements.txt`](../scripts/requirements.txt). If it is missing, the launcher creates a local `.venv` and installs it there. This requires an internet connection once.
- Git and [GitHub CLI](https://cli.github.com/) for publishing. Sign in once with `gh auth login` and configure your Git commit name and email if this is a new computer.
- Use a **Git clone**, not a downloaded ZIP, when publishing. The existing repository on the current computer is already configured.

For a new computer:

```powershell
gh auth login
git clone https://github.com/QMInmu/marginalia.git
cd marginalia
.\更新资料库.cmd
```

## Files and organization

Supported formats: PDF, DOC/DOCX, PPT/PPTX, XLS/XLSX, CSV, TXT, Markdown, PNG, JPG/JPEG, WebP, GIF, ZIP, 7z, and RAR. PDFs show a page count; other formats show their file type and size. Some formats download instead of opening inside the browser.

```text
courses/
├── 电路测试实验/
│   ├── 实验讲义/
│   ├── 课件/
│   └── ...
└── 模拟电子技术/
    └── 课件/
        └── 第1章.pptx
```

Folder import includes supported files in subfolders and retains their relative structure. Hidden folders, folders beginning with `_`, Office temporary files, and unsupported extensions are skipped. A different course is created by selecting **新建课程**; do not select a folder containing several unrelated courses in one import.

An identical file at the same destination is skipped. A different file with the same destination name requires an explicit replacement choice. The tool validates all selected files before copying and restores previous local files if a write fails. Password-protected or unreadable PDFs are rejected before copying.

Files larger than **100 MiB** are rejected because [GitHub blocks them in regular Git repositories](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github). Split or compress such files before importing them.

## Command line

Run from the repository root. The examples use `python`; use `py -3` or the `.venv` Python executable if that is how Python is installed on your computer.

```powershell
# List existing courses and categories.
python scripts/update_library.py list

# Preview without writing or uploading anything.
python scripts/update_library.py add --course "模拟电子技术" --english-name "Analog Electronics" --category "课件" --dry-run "D:\Study\第1章.pptx"

# Import a new course and publish it.
python scripts/update_library.py add --course "模拟电子技术" --english-name "Analog Electronics" --category "课件" --publish "D:\Study\第1章.pptx"

# Add multiple files to an existing course, keeping them local for now.
python scripts/update_library.py add --course "电路测试实验" --category "复习总结" "D:\Study\笔记.pdf" "D:\Study\补充说明.docx"

# Import a folder; explicitly allow replacement of different namesakes.
python scripts/update_library.py add --course "模拟电子技术" --category "课件" --replace "D:\Study\Slides"

# Scan files already copied into registered course/category folders.
python scripts/update_library.py sync
python scripts/update_library.py sync --check

# Publish saved local changes; wait for the live catalog to match.
python scripts/update_library.py publish
```

Use `--no-wait` with `publish` or `--publish` to return after pushing. Website publishing still runs on GitHub. If you intentionally deleted or renamed previously indexed files, run `sync --allow-removals` before publishing. This flag only permits removing missing entries from the generated catalog; it does not delete files.

## Configuration and recovery

- [`library.json`](../library.json) holds the course names, descriptions, category folders, repository URL, and website URL. New courses and categories are added by the updater. English names are optional; when omitted, the original Chinese name is shown in both languages until you edit the English name in this file.
- `catalog.json`, the root `README.md`, and each course `README.md` are **generated files**. Do not put personal edits there; add separate documents or update the generator instead. After editing `library.json`, run `sync`.
- The tool checks the configured origin and branch, fetches remote changes, and only fast-forwards a clean checkout. It stops on conflicts, unrelated local changes, or an already populated staging area. It never force-pushes.
- If uploading fails, your imported files and generated indexes remain local. Fix authentication or the network connection and run `publish` again. A failed push can leave a local `Update learning materials` commit; the next publish retries it.
- Exit code `0` means success, `1` means an error, and `2` means the push succeeded but the live catalog was not verified before the waiting period ended. Check the repository’s [Actions page](https://github.com/QMInmu/marginalia/actions) in the last case.
- The current Pages site publishes from `main` at the repository root. [GitHub republishes it when that branch is updated](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site); the script does not change the Pages settings.

## 中文操作指南

### 平时添加一门新课

1. 双击本地仓库里的 **更新资料库.cmd**。当前电脑也可使用“电测实验”文件夹里的 **更新学习资料库.cmd** 快捷入口。
2. 选择 **添加资料 → 新建课程**。
3. 输入课程中文名称，例如“模拟电子技术”；英文名称可填写 `Analog Electronics`，也可先留空。
4. 选择分类，例如“课件”“讲义”“试题与解析”，也可以新建分类。
5. 选择“弹窗多选文件”，按住 Ctrl 多选；或选择一个课程、一个分类对应的文件夹。
6. 查看新增、跳过和替换清单，选择 **上传并更新网站**。
7. 看到“网站目录已更新”后，打开 [Marginalia](https://qminmu.github.io/marginalia/)。新课程会出现在网站左侧课程目录中。

### 给已有课程补资料

选择 **添加资料**，再选择已有课程和分类即可。内容完全相同的同名文件会跳过；不同内容的同名文件会让你选择“跳过”“允许替换”或“取消”，不会悄悄覆盖。

### 先整理、稍后上传

完成方式选择 **仅保存到本地**。之后双击入口，选择 **上传之前已保存的更新**。脚本会一并上传本地已整理的资料并更新目录。

### 直接往课程文件夹里放文件

可以把文件复制到**已有且已登记的课程/分类文件夹**，再选择 **扫描课程文件夹，更新目录**。新课程或新分类优先通过“添加资料”建立，不需要手工改 JSON。整个原始资料文件夹不会自动上传，只有实际导入或放入登记分类的支持格式文件才会收录。

### 遇到问题

- **显示同名冲突**：检查清单，确认新文件是更新版本后再选择“允许替换”。
- **登录过期或网络错误**：文件仍在本地；重新登录 `gh auth login` 或恢复网络后，选择“上传之前已保存的更新”。
- **远端比本地新、暂存区已有改动或出现其他修改**：按提示先处理 Git 状态，再重试。脚本不会覆盖这些改动。
- **已推送，但网站尚未核验**：先查看 [Actions](https://github.com/QMInmu/marginalia/actions) 是否完成，再刷新网页。脚本只在公开目录与本地目录一致时显示“网站目录已更新”。
- **已主动删除/改名的文件被提示缺失**：在仓库目录运行 `python scripts/update_library.py sync --allow-removals`，核对后再发布。

原始中文文件名和文件内容保持不变；生成目录所需的页数、文件大小和 SHA-256 校验值会自动更新。源文件留在原位置，发布副本位于本地仓库的 `courses/` 下。
