/**
 * ResearchExpHub — ECharts helper utilities
 */

var DEFAULT_COLORS = [
    '#1f77b4','#ff7f0e','#2ca02c','#d62728','#9467bd',
    '#8c564b','#e377c2','#7f7f7f','#bcbd22','#17becf'
];

function initEmptyChart(domId, message) {
    var el = document.getElementById(domId);
    if (!el) return;
    var chart = echarts.init(el);
    chart.setOption({
        title: {
            text: message,
            left: "center",
            top: "center",
            textStyle: { color: "#999", fontSize: 16, fontWeight: "normal" },
        },
    });
    window.addEventListener("resize", function () {
        chart.resize();
    });
    return chart;
}

function renderLineChart(domId, title, xData, series) {
    var el = document.getElementById(domId);
    if (!el) return;
    var chart = echarts.init(el);
    chart.setOption({
        title: { text: title },
        tooltip: { trigger: "axis" },
        legend: { bottom: 0 },
        xAxis: { type: "category", data: xData },
        yAxis: { type: "value" },
        series: series,
    });
    window.addEventListener("resize", function () {
        chart.resize();
    });
    return chart;
}

/**
 * Render a multi-series chart from the /api/experiments/{eid}/metrics response.
 * Returns the ECharts instance.
 */
function renderMetricsChart(domId, data, showBest, chartType) {
    var el = document.getElementById(domId);
    if (!el) return null;
    var chart = echarts.getInstanceByDom(el);
    if (!chart) chart = echarts.init(el);

    chartType = chartType || 'line';
    var legendData = [];
    var seriesArr = [];
    var xLabel = data.x_axis || 'x';

    data.series.forEach(function(s, idx) {
        var color = DEFAULT_COLORS[idx % DEFAULT_COLORS.length];
        legendData.push(s.metric_name);

        var seriesItem = {
            name: s.metric_name,
            data: s.points.map(function(p){ return [p.x, p.y]; }),
            itemStyle: { color: color },
        };

        if (chartType === 'bar') {
            seriesItem.type = 'bar';
            seriesItem.barMaxWidth = 30;
        } else if (chartType === 'scatter') {
            seriesItem.type = 'scatter';
            seriesItem.symbolSize = 6;
        } else if (chartType === 'area') {
            seriesItem.type = 'line';
            seriesItem.smooth = true;
            seriesItem.areaStyle = { opacity: 0.25 };
            seriesItem.symbol = 'circle';
            seriesItem.symbolSize = 3;
            seriesItem.lineStyle = { color: color, width: 2 };
        } else if (chartType === 'step') {
            seriesItem.type = 'line';
            seriesItem.step = 'middle';
            seriesItem.symbol = 'none';
            seriesItem.lineStyle = { color: color, width: 2 };
        } else {
            seriesItem.type = 'line';
            seriesItem.smooth = false;
            seriesItem.symbol = 'circle';
            seriesItem.symbolSize = 4;
            seriesItem.lineStyle = { color: color, width: 2 };
        }

        seriesArr.push(seriesItem);

        // best point marker
        if (showBest && s.best_point) {
            seriesArr.push({
                name: s.metric_name + ' best',
                type: 'scatter',
                data: [[s.best_point.x, s.best_point.y]],
                symbol: 'pin',
                symbolSize: 28,
                itemStyle: { color: color },
                label: {
                    show: true,
                    formatter: function(p){ return p.value[1].toFixed(4); },
                    position: 'top',
                    fontSize: 10,
                },
                tooltip: {
                    formatter: function(p){
                        return s.metric_name + ' best<br/>' + xLabel + ': ' + p.value[0] + '<br/>value: ' + p.value[1];
                    }
                },
                z: 10,
            });
        }
    });

    chart.setOption({
        title: { text: data.experiment_name, left: 'center', textStyle: { fontSize: 14 } },
        tooltip: {
            trigger: 'axis',
            formatter: function(params) {
                if (!params || !params.length) return '';
                var html = '<strong>' + xLabel + ': ' + params[0].value[0] + '</strong>';
                params.forEach(function(p){
                    if (p.seriesType === 'scatter') return;
                    html += '<br/>' + p.marker + ' ' + p.seriesName + ': ' + p.value[1].toFixed(6);
                });
                return html;
            }
        },
        legend: { data: legendData, bottom: 0, type: 'scroll' },
        grid: { left: 60, right: 30, top: 50, bottom: 50 },
        xAxis: { type: 'value', name: xLabel, nameLocation: 'center', nameGap: 30 },
        yAxis: { type: 'value', scale: true },
        dataZoom: [
            { type: 'inside', xAxisIndex: 0 },
            { type: 'slider', xAxisIndex: 0, bottom: 25, height: 15 },
        ],
        toolbox: {
            right: 10,
            feature: {
                saveAsImage: { title: '保存 PNG' },
                dataZoom: { title: { zoom: '缩放', back: '还原' } },
                restore: { title: '重置' },
            }
        },
        color: DEFAULT_COLORS,
        series: seriesArr,
    }, true);

    window.addEventListener("resize", function () { chart.resize(); });
    return chart;
}

/**
 * Render a summary table into domId from series data.
 */
function renderSummaryTable(domId, series) {
    var el = document.getElementById(domId);
    if (!el) return;
    if (!series || !series.length) {
        el.innerHTML = '<p class="text-muted mb-0">暂无指标数据。</p>';
        return;
    }
    var html = '<div class="table-responsive"><table class="table table-sm table-hover mb-0">';
    html += '<thead class="table-light"><tr>';
    html += '<th>指标名</th><th>方向</th><th>最佳值</th><th>最佳位置</th><th>最后值</th><th>最后位置</th><th>数据量</th>';
    html += '</tr></thead><tbody>';
    series.forEach(function(s) {
        var dirLabel = s.direction === 'lower_better' ? '↓ 越小越好' : '↑ 越大越好';
        var bestVal = s.best_point ? s.best_point.y.toFixed(6) : '-';
        var bestX = s.best_point ? s.best_point.x : '-';
        var lastVal = s.last_point ? s.last_point.y.toFixed(6) : '-';
        var lastX = s.last_point ? s.last_point.x : '-';
        html += '<tr>';
        html += '<td><strong>' + s.metric_name + '</strong></td>';
        html += '<td><small>' + dirLabel + '</small></td>';
        html += '<td>' + bestVal + '</td>';
        html += '<td>' + bestX + '</td>';
        html += '<td>' + lastVal + '</td>';
        html += '<td>' + lastX + '</td>';
        html += '<td>' + (s.point_count || s.points.length) + '</td>';
        html += '</tr>';
    });
    html += '</tbody></table></div>';
    el.innerHTML = html;
}
