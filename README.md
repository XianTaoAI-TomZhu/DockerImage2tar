# Docker Image to Tar

一个无需 Docker 即可从镜像仓库拉取 Docker 镜像并保存为 tar 文件的工具。

## 特性

- 🚀 **无需 Docker**：直接使用 Python 脚本运行
- 🌐 **多仓库支持**：默认使用国内镜像加速，支持多个备用仓库
- 🔄 **断点续传**：下载中断后自动继续
- 📦 **并发下载**：支持多线程加速下载
- ✅ **自动重试**：失败后自动重试，最多 10 次
- 🔍 **SHA256 校验**：下载后自动校验文件完整性
- 🏗️ **多架构**：支持 amd64, arm64 等多种架构
- 🔐 **私有仓库**：支持带认证的私有镜像仓库
- 💻 **友好 CLI**：命令行参数和交互式输入

## 环境要求

- Python 3.8+

## 安装

```bash
git clone <repository>
cd DockerImage2tar
pip install -r requirements.txt
```

## 快速开始

### 基本使用

```bash
python main.py -i nginx:latest
```

### 命令行参数

| 参数 | 说明 |
|------|------|
| `-i, --image` | 镜像名称，例如 `nginx:latest` 或 `harbor.example.com/library/nginx:1.26.0` |
| `-a, --arch` | 架构，默认 `amd64`，可选 `arm64`, `armv7`, `ppc64le`, `s390x` |
| `-r, --custom-registry` | 自定义仓库地址 |
| `-u, --username` | 仓库用户名 |
| `-p, --password` | 仓库密码 |
| `-o, --output` | 输出目录，默认为当前目录 |
| `-q, --quiet` | 静默模式 |
| `--debug` | 调试模式 |
| `--workers` | 并发线程数，默认 4 |
| `-v, --version` | 显示版本 |
| `-h, --help` | 显示帮助 |

## 使用示例

### 下载最新版 Nginx

```bash
python main.py -i nginx:latest
```

### 下载指定架构

```bash
python main.py -i alpine:latest -a arm64
```

### 使用私有仓库

```bash
python main.py -i harbor.example.com/library/nginx:1.26.0 -u admin -p password
```

### 指定输出目录

```bash
python main.py -i nginx:latest -o ./downloads
```

### 静默模式

```bash
python main.py -i nginx:latest -q
```

### 交互式模式

```bash
python main.py
```

## 导入镜像

将 tar 文件传输到目标机器后，使用 Docker 导入：

```bash
docker load -i library_nginx_latest.tar
```

验证：

```bash
docker images
```

## 镜像仓库

### 默认仓库

默认使用 `https://docker-pull.ygxz.in/` 镜像加速器

### 备用仓库

如果默认仓库不可用，会自动尝试：

- https://docker.1panel.live/
- https://1ms.run/
- https://proxy.vvvv.ee
- https://docker.m.daocloud.io
- https://registry.cyou

### 自定义仓库

```bash
python main.py -i nginx:latest -r https://docker.io
```

## 项目结构

```
DockerImage2tar/
├── main.py                 # 主程序
├── test.py                 # 测试
├── requirements.txt        # 依赖
├── README.md              # 本文档
└── docker_puller/
    ├── __init__.py        # 版本信息
    ├── cli.py             # 命令行处理
    ├── registry.py        # Registry API 客户端
    ├── downloader.py      # 下载管理器
    ├── tar_builder.py    # Tar 文件构建
    ├── utils.py          # 工具函数
    └── progress.py        # 进度显示
```

## 许可证

MIT License
