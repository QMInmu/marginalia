# Marginalia · 书页之间

A personal collection of learning materials, organized by course. A place for the pages worth keeping.

[Browse the library](https://qminmu.github.io/marginalia/) · [Update guide / 更新指南](docs/UPDATING.md) · [中文说明](#中文说明)

The website opens in English and includes a Chinese language switch. Original Chinese filenames are preserved.

## Courses

| Course | Materials | Contents |
| --- | ---: | --- |
| [Electrical Circuit Testing Laboratory · 电路测试实验](courses/%E7%94%B5%E8%B7%AF%E6%B5%8B%E8%AF%95%E5%AE%9E%E9%AA%8C/README.md) | 26 files · 55.6 MiB | Exams &amp; solutions: 4; Lab handouts: 10; Lecture slides: 7; Textbooks &amp; lab reports: 4; Review notes: 1 |

## Browse and download

- Use the [website](https://qminmu.github.io/marginalia/) to select a course, filter by category, and search filenames.
- Open supported documents in your browser or download the original files.
- Browse [`courses/`](courses/), or use **Code → Download ZIP** to download the repository.

## Add materials

On Windows, double-click **更新资料库.cmd** in your local clone. Choose or create a course, select a category and files, then choose **上传并更新网站**. The updater copies the files, rebuilds the website catalog and course indexes, commits, and pushes the update.

PDFs, Office documents, images, text files, and archives are supported. See the [update guide](docs/UPDATING.md) for setup, command-line examples, and replacing files. Course settings live in `library.json`; `catalog.json` and the course indexes are generated automatically.

## 中文说明

**书页之间**是按课程整理的个人学习资料库，现有 **1 门课程、26 份资料**。网页默认英文，可切换中文，保留原有中文文件名和文件内容。

添加资料时，在本地仓库双击 **更新资料库.cmd**，依次选择课程、分类和文件，再选择“上传并更新网站”。脚本会自动更新网站目录和各课程索引，无需手工修改 JSON。详细操作见[更新指南](docs/UPDATING.md#中文操作指南)。
