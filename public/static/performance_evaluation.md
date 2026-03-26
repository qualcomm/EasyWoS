# 性能评估

Qualcomm Top-Down Tool 是一个 Windows Performance Analyzer (WPA) 插件，帮助开发者分析WoS平台上的性能问题，从应用层一直到 CPU微架构层。

Top-Down 方法是指从高层指标开始性能分析，并逐步深入到更详细的指标。这些指标源自 PMU (Performance Monitoring Unit) 事件，可以使用 Windows Performance Recorder (WPR) 进行收集。

下载 [Qualcomm Top-Down Tool 插件](https://github.com/qualcomm/TopDown-WPA-Plugin-for-Qualcomm-Oryon/releases)

## 性能指标

基于标准的 ARM Neoverse N3 架构指标，我们列出了目前 Oryon 架构 CPU (HM & GL) 支持的指标，以及用于计算这些指标的相应 PMU 事件。红色单元格表示 Oryon CPU 不支持的指标。

![performance_metrics_01.png](/static/pics/performance_metrics_01.png)

![performance_metrics_02.png](/static/pics/performance_metrics_02.png)

![performance_metrics_03.png](/static/pics/performance_metrics_03.png)

![performance_metrics_04.png](/static/pics/performance_metrics_04.png)

![performance_metrics_05.png](/static/pics/performance_metrics_05.png)

![performance_metrics_06.png](/static/pics/performance_metrics_06.png)

![performance_metrics_07.png](/static/pics/performance_metrics_07.png)

![performance_metrics_08.png](/static/pics/performance_metrics_08.png)

由于硬件限制，无法在单个配置文件中捕获所有 PMU 事件。因此，我们在单个 .wprp 文件中包含多个配置文件，每个配置文件通过计算性能指标的特定子集来设计，如下表所示。

![metrics_group_01.png](/static/pics/metrics_group_01.png)

![metrics_group_02.png](/static/pics/metrics_group_02.png)

![metrics_group_03.png](/static/pics/metrics_group_03.png)

## 如何使用
要收集 PMU 事件，首先应使用带有 .wprp 文件的 WPR，特别是选择 General 配置文件来捕获关键性能指标，例如每周期指令数 (Instructions Per Cycle) 和退休 (Retiring)，这有助于确定有用工作的比例。

如果发现有用工作率较低，则应分析错误推测 (Bad Speculation)，并检查分支预测相关指标是否存在异常。

否则，应检查问题是前端受限 (Frontend Bound) 还是后端受限 (Backend Bound)，并进一步确定是核心受限 (Core Bound) 还是内存受限 (Memory Bound)。

### 收集 PMU 事件

#### 使用 WPR GUI 收集 PMU 事件
通过将 .wprp 文件导入 WPR GUI，我们可以访问专为收集 PMU 事件而设计的自定义测量配置文件。

![collect_pmu_event_01.png](/static/pics/collect_pmu_event_01.png)

选择所需的配置文件后，点击 `Start` 开始收集 PMU 事件。请注意，除非绝对必要，否则不应包含 First Level Triage 配置文件，因为它会显著增加 ETL 文件的大小。

一旦成功复现测试场景，点击 `Save` 保存生成的 ETL 文件。

![collect_pmu_event_02.png](/static/pics/collect_pmu_event_02.png)
![collect_pmu_event_03.png](/static/pics/collect_pmu_event_03.png)
![collect_pmu_event_04.png](/static/pics/collect_pmu_event_04.png)

#### 使用 WPR CLI 收集 PMU 事件
所有可以通过 GUI 进行的操作也可以使用命令行执行。

我们可以通过 CLI 使用 General 配置文件收集 PMU 事件，如下所示。
```powershell
wpr -start "path/to/wprp!General"
```
在我们成功复现测试场景后，我们可以像这样保存 .etl 文件。
```powershell
wpr -stop filename.etl "description"
```
![collect_pmu_event_05.png](/static/pics/collect_pmu_event_05.png)

### 安装 WPA 插件
您可以从发布页面下载适用于目标架构的 QcTopDown.ptix 文件，并将其安装到 WPA 中。
如果 Qualcomm Top-Down Plugin 出现在 WPA 中，则表明安装成功。

![install_wpa_plugin_01.png](/static/pics/install_wpa_plugin_01.png)
![install_wpa_plugin_02.png](/static/pics/install_wpa_plugin_02.png)

### 使用 TopDown Tool 打开 ETL 文件
打开 ETL 文件时，我们将看到几个查看选项。

我们可以选择使用 `Qualcomm TopDown Tool` 打开它来分析 PMU 事件和性能指标。同时，您也可以使用 Event Tracing for Windows (ETW) 打开它以查看一般系统信息。
![open_etl_01.png](/static/pics/open_etl_01.png)

使用 Qualcomm Top-Down Tool 打开 .etl 文件后，您可以将所需的缩略图视图从左侧面板拖到右侧分析窗格。这使您可以查看详细的性能指标以进行深入分析。
![open_etl_02.png](/static/pics/open_etl_02.png)

同时，您可以查看原始 PMU 事件并将其添加到所需的缩略图视图中。这有助于增强我们的分析。
![open_etl_02.png](/static/pics/open_etl_02.png)

## 案例研究

[下载 Analyze CPU-Z through WPA plugin.pdf](/static/docs/Analyze%20CPU-Z%20through%20WPA%20plugin.pdf)

[下载 WPS Producer–Consumer Architecture Optimization.pdf](/static/docs/WPS%20Producer–Consumer%20Architecture%20Optimization.pdf)


