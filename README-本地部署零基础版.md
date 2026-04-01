# README-本地部署零基础版

面向对象：
- 完全不会写代码 / 只想“点几下就能跑起来”的同学
- 想在 **自己电脑本地** 打开本项目网页，进行单车调度仿真

只要按下面步骤一步步来，一般 10–20 分钟可以跑起来。

---

## 一、准备工作（所有人都要做）

### 1. 安装 Python 3

1. 打开浏览器，访问 Python 官网：https://www.python.org/downloads/
2. 下载 Windows 版本（比如 Python 3.10/3.11）。
3. 安装时 **务必勾选**：`Add Python to PATH`，然后一路下一步。

安装好后，按 `Win + R` 输入 `cmd` 回车，在黑框里输入：

```bash
python --version
```

看到类似：

```text
Python 3.10.x
```

说明 Python 安装成功。

---

## 二、方案一：从 GitHub 拉取代码（推荐）

适合：
- 会安装 Git，或者愿意多装一个小软件的同学
- 以后还可能更新代码、拉最新版本

### 1. 安装 Git（如果已经装过可跳过）

1. 打开浏览器，访问：https://git-scm.com/downloads
2. 下载 Windows 版本，双击安装包，一路下一步即可（默认选项就好）。

安装好后，按 `Win + R` 输入 `cmd` 回车，在黑框里输入：

```bash
git --version
```

能看到版本号说明安装成功。

### 2. 从 GitHub 克隆项目

1. 找一个你想存放项目的文件夹，例如：`D:\Projects`。（也可以是桌面）
2. 在该文件夹空白处按住 `Shift` + 右键，选择“在此处打开 PowerShell 窗口”或“在此处打开命令窗口”。
3. 在终端里输入：

```bash
git clone https://github.com/North517/Sharing-bike.git
```

执行完成后，会多出一个文件夹：`Sharing-bike`，里面就是项目代码。

### 3. 基于系统自带 Python 的方式（普通用户）

后续命令都在 `Sharing-bike` 目录里执行。

```bash
cd Sharing-bike
```

创建虚拟环境（只需做一次）：

```bash
python -m venv venv
```

激活虚拟环境（每次重新打开终端，都需要先激活一次）：

```bash
venv\Scripts\activate
```

如果成功，命令行最前面会出现：

```text
(venv) C:\...>
```

安装项目所需依赖（只需安装一次）：

```bash
pip install -r requirements.txt
```

启动项目：

```bash
python app.py
```

终端看到类似：

```text
Running on http://127.0.0.1:5000/
```

在浏览器中访问：

```text
http://127.0.0.1:5000/
```

即可看到项目首页。

> 后续再次使用：
>
> 1. 进入项目目录 `Sharing-bike`
> 2. 激活虚拟环境：`venv\Scripts\activate`
> 3. 启动项目：`python app.py`
> 4. 浏览器访问 `http://127.0.0.1:5000/`

---

### 4. 基于 Conda 环境的方式（适合已安装 Anaconda/Miniconda 的同学）

如果你电脑上已经装了 Anaconda 或 Miniconda，推荐用 Conda 来管理环境。

#### 4.1 打开 Conda 终端

- 在开始菜单中搜索并打开：`Anaconda Prompt`（或者你常用的 Conda 终端）。
- 在终端中先进入项目目录，例如：

```bash
cd D:\Projects\Sharing-bike
```

（根据你实际的项目路径修改。）

#### 4.2 创建 Conda 环境

创建一个仅用于本项目的环境（名字可以自定义，这里叫 `bike-sim`）：

```bash
conda create -n bike-sim python=3.10
```

> 如果你不确定用哪个版本，可以直接使用上面的 `python=3.10`。

#### 4.3 激活 Conda 环境

环境创建完成后，执行：

```bash
conda activate bike-sim
```

激活成功后，命令行前面会出现：

```text
(bike-sim) C:\...>
```

#### 4.4 在 Conda 环境中安装依赖

确保当前终端前缀是 `(bike-sim)`，然后执行：

```bash
pip install -r requirements.txt
```

> 说明：虽然是 Conda 环境，但这里依然使用 `pip` 安装本项目的依赖。

#### 4.5 启动项目

仍然在 `(bike-sim)` 环境中，执行：

```bash
python app.py
```

看到类似：

```text
Running on http://127.0.0.1:5000/
```

在浏览器中访问：

```text
http://127.0.0.1:5000/
```

即可使用项目。

> 后续再次使用（Conda 版）：
>
> 1. 打开 `Anaconda Prompt`
> 2. 激活环境：`conda activate bike-sim`
> 3. 进入项目目录：`cd D:\Projects\Sharing-bike`
> 4. 启动项目：`python app.py`
> 5. 浏览器访问 `http://127.0.0.1:5000/`

---

## 三、方案二：直接用压缩包（不想用 Git 的同学）

适合：
- 懒得安装 Git
- 直接让别人把“压缩好的项目文件夹”发给你

### 1. 获取项目压缩包

请同学把项目根目录（例如 `Sharing-bike` 或 `FleetPy-main`）压缩成 zip，发给你（QQ / 微信 / 网盘均可）。

你只需要：

1. 把压缩包下载到本地，比如：`D:\Sharing-bike.zip`
2. 右键压缩包 → 解压到当前文件夹
3. 解压完成后，得到一个项目文件夹，例如：`D:\Sharing-bike`

后续步骤与方案一 **完全一样**：可以选“系统自带 Python 的方式”，也可以使用 Conda 环境。

### 2. 使用系统自带 Python 的方式

```bash
cd D:\Sharing-bike
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### 3. 使用 Conda 环境的方式

打开 `Anaconda Prompt`，然后：

```bash
cd D:\Sharing-bike
conda create -n bike-sim python=3.10
conda activate bike-sim
pip install -r requirements.txt
python app.py
```

终端看到 `Running on http://127.0.0.1:5000/` 后，在浏览器中访问这个地址即可。

---

## 四、常见问题 Q&A

### Q1. `python` 命令报错：“不是内部或外部命令”

**原因**：Python 没装好，或者安装时没有勾选 `Add Python to PATH`。

**解决办法**：
1. 重新安装 Python：卸载后，从官网重新安装。
2. 安装时务必勾选 `Add Python to PATH`。
3. 安装结束后，重新打开终端，再输入：

```bash
python --version
```

确认能看到版本号。

> 如果你使用的是 Conda 环境：
> - 请确保在 `Anaconda Prompt` 中，并且已经 `conda activate bike-sim` 之后再执行 `python` 命令。

---

### Q2. `pip` 命令报错，或者安装包太慢

**情况 1：提示 pip 不是命令**

说明 Python 安装环境变量不完整或终端没重启，尝试：

```bash
python -m pip --version
```

如果能看到版本号，后续所有 `pip` 命令可以写成：

```bash
python -m pip install -r requirements.txt
```

如果你在 Conda 环境中，也建议使用上面的写法。

**情况 2：安装太慢、经常卡住**

可以先尝试国内镜像，例如：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

或：

```bash
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

### Q3. `python -m venv venv` 失败

常见原因：
- 权限不够（尽量不要放在中文路径、桌面奇怪目录）
- 系统 Python 被某些安全软件限制

**建议**：
- 把项目放在简单路径，比如：`D:\Projects\Sharing-bike`
- 用管理员身份打开 PowerShell 再试一次。
- 或者直接使用 Conda 环境创建方式（`conda create -n bike-sim python=3.10`），不再依赖 `venv`。

---

### Q4. 启动后访问不了网页 / 浏览器打不开

请按顺序排查：

1. 终端中 `python app.py` 是否有报错？如果有错误信息，优先解决错误（可以截图问会写代码的同学）。
2. 是否看到 `Running on http://127.0.0.1:5000/` 这行提示？
3. 浏览器地址栏是否完整输入：
   
   ```text
   http://127.0.0.1:5000/
   ```

4. 如果你安装了杀毒软件 / 防火墙，它可能会阻止本地端口，试着允许 Python 程序访问本地网络。
5. 如果端口被占用，可以尝试在 `app.py` 中修改端口号（需要一点点 Python 基础，可请教会写代码的同学）。

---

### Q5. 我关闭了终端 / 电脑重启了，还能再用吗？

可以，按照下面步骤重新启动即可：

**使用系统自带 Python 的情况：**

1. 打开终端（PowerShell / CMD）。
2. 进入项目目录，比如：

   ```bash
   cd D:\Sharing-bike
   ```

3. 激活虚拟环境：

   ```bash
   venv\Scripts\activate
   ```

4. 启动项目：

   ```bash
   python app.py
   ```

5. 浏览器访问：

   ```text
   http://127.0.0.1:5000/
   ```

**使用 Conda 环境的情况：**

1. 打开 `Anaconda Prompt`。
2. 激活环境：

   ```bash
   conda activate bike-sim
   ```

3. 进入项目目录：

   ```bash
   cd D:\Sharing-bike
   ```

4. 启动项目：

   ```bash
   python app.py
   ```

5. 浏览器访问：

   ```text
   http://127.0.0.1:5000/
   ```

依赖只需安装一次，之后每次只要“激活环境 + 启动项目 + 打开浏览器”就行。

---

### Q6. 不会用命令行，看了还是懵怎么办？

可以让熟悉电脑的同学远程协助（QQ/微信远程），只要照着本文件操作 1 次，他学会之后，后面就可以自己帮你启动项目。

你也可以把这份《README-本地部署零基础版》直接发给他，他看完基本就知道怎么帮你部署了。
