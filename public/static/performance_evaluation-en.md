# Performance Evaluation

The Qualcomm Top-Down Tool is a Windows Performance Analyzer (WPA) plugin that helps developers analyze performance issues on the WoS platform, from the application level down to the CPU microarchitecture level.

The Top-Down approach refers to starting performance analysis from high-level metrics and progressively drilling down into more detailed ones. These metrics are derived from PMU (Performance Monitoring Unit) events, which can be collected using Windows Performance Recorder (WPR).

Download the [Qualcomm Top-Down Tool plugin](https://github.com/qualcomm/TopDown-WPA-Plugin-for-Qualcomm-Oryon/releases)

## Performance Metrics

Based on standard ARM Neoverse N3 architecture metrics, we have listed the metrics currently supported by the Oryon architecture CPU (HM & GL), along with the corresponding PMU events used for their calculation. Red cells indicate metrics not supported by the Oryon CPU.

![performance_metrics_01.png](/static/pics/performance_metrics_01.png)

![performance_metrics_02.png](/static/pics/performance_metrics_02.png)

![performance_metrics_03.png](/static/pics/performance_metrics_03.png)

![performance_metrics_04.png](/static/pics/performance_metrics_04.png)

![performance_metrics_05.png](/static/pics/performance_metrics_05.png)

![performance_metrics_06.png](/static/pics/performance_metrics_06.png)

![performance_metrics_07.png](/static/pics/performance_metrics_07.png)

![performance_metrics_08.png](/static/pics/performance_metrics_08.png)

Due to hardware limitations, it's not possible to capture all PMU events in a single profile. Therefore, we include multiple profiles within a single .wprp file, each designed to calculate a specific subset of performance metrics, as detailed in the table below.

![metrics_group_01.png](/static/pics/metrics_group_01.png)

![metrics_group_02.png](/static/pics/metrics_group_02.png)

![metrics_group_03.png](/static/pics/metrics_group_03.png)

## How to use
To collect PMU events, you should first use WPR with a .wprp file, specifically selecting the General profile to capture key performance metrics such as Instructions Per Cycle and Retiring, which help determine the proportion of useful work.

If you find that the useful work rate is low, then you should analyze Bad Speculation and check whether there are any anomalies in branch prediction-related metrics.

Otherwise, you should check whether the issue is Frontend Bound or Backend Bound, and further determine whether it is Core Bound or Memory Bound.

### Collect PMU event

#### Use WPR GUI to collect PMU event
By importing the .wprp file into the WPR GUI, we can access custom measurement profiles specifically designed for collecting PMU events.

![collect_pmu_event_01.png](/static/pics/collect_pmu_event_01.png)

After selecting the desired profile, click `Start` to begin PMU event collection. Please note that the First Level Triage profile should not be included unless absolutely necessary, as it significantly increases the size of the ETL file.

Once the test scenario has been successfully reproduced, click `Save` to store the resulting ETL file.

![collect_pmu_event_02.png](/static/pics/collect_pmu_event_02.png)
![collect_pmu_event_03.png](/static/pics/collect_pmu_event_03.png)
![collect_pmu_event_04.png](/static/pics/collect_pmu_event_04.png)

#### Use WPR CLI to collect PMU event
All operations available through the GUI can alternatively be executed using the command line.

We can collect PMU events using the General profile by CLI as follows.
```powershell
wpr -start "path/to/wprp!General"
```
After we successfully reproduce the test scenario, we can save the .etl file like this.
```powershell
wpr -stop filename.etl "description"
```
![collect_pmu_event_05.png](/static/pics/collect_pmu_event_05.png)

### Install WPA Plugin
You can download the appropriate QcTopDown.ptix file for your target architecture from the release page and install it into WPA.
If the Qualcomm Top-Down Plugin appears in WPA, it indicates that the installation was successful.

![install_wpa_plugin_01.png](/static/pics/install_wpa_plugin_01.png)
![install_wpa_plugin_02.png](/static/pics/install_wpa_plugin_02.png)

### Open ETL file with TopDown Tool
When opening the ETL file, we will be presented with several viewing options.

We can choose to open it with the `Qualcomm TopDown Tool` to analyze PMU events and performance metrics. At the same time, you can also open it with Event Tracing for Windows (ETW) to view general system information.
![open_etl_01.png](/static/pics/open_etl_01.png)

After opening the .etl file with the Qualcomm Top-Down Tool, you can drag the desired thumbnail view from the left panel to the right analysis pane. This allows you to view detailed performance metrics for in-depth analysis.
![open_etl_02.png](/static/pics/open_etl_02.png)

At the same time, you can view the raw PMU events and add them to the desired thumbnail view. This helps enhance our analysis.
![open_etl_02.png](/static/pics/open_etl_02.png)

## Case Study

[Download Analyze CPU-Z through WPA plugin.pdf](/static/docs/Analyze%20CPU-Z%20through%20WPA%20plugin.pdf)

[Download WPS Producer–Consumer Architecture Optimization.pdf](/static/docs/WPS%20Producer–Consumer%20Architecture%20Optimization.pdf)
