"""
SciFigLab — 学科领域配置 + 学科特定数据格式映射
"""

from typing import Dict, List

# ---------------------------------------------------------------------------
# 1. RESEARCH_AREAS — 全学科覆盖
# ---------------------------------------------------------------------------
RESEARCH_AREAS: Dict[str, str] = {
    # 计算机与AI
    "deep_learning":        "深度学习 / Deep Learning",
    "machine_learning":     "机器学习 / Machine Learning",
    "computer_vision":      "计算机视觉 / CV",
    "nlp":                  "自然语言处理 / NLP",
    "reinforcement_learning": "强化学习 / RL",
    "data_mining":          "数据挖掘 / Data Mining",
    "computer_science":     "计算机科学(通用)",
    # 数学与统计
    "mathematics":          "数学 / Mathematics",
    "statistics":           "统计学 / Statistics",
    # 物理
    "physics_general":      "物理学(通用)",
    "optics":               "光学 / Optics",
    "quantum_physics":      "量子物理",
    "condensed_matter":     "凝聚态物理",
    "astrophysics":         "天体物理",
    # 化学
    "chemistry_general":    "化学(通用)",
    "organic_chemistry":    "有机化学",
    "analytical_chemistry": "分析化学",
    "physical_chemistry":   "物理化学",
    "biochemistry":         "生物化学",
    # 生物
    "biology_general":      "生物学(通用)",
    "molecular_biology":    "分子生物学",
    "genomics":             "基因组学 / Genomics",
    "ecology":              "生态学",
    "neuroscience":         "神经科学",
    # 医学
    "medicine":             "医学(通用)",
    "clinical_medicine":    "临床医学",
    "medical_imaging":      "医学影像",
    "pharmacology":         "药理学",
    "public_health":        "公共卫生",
    # 工程
    "electrical_engineering": "电气/电子工程",
    "mechanical_engineering": "机械工程",
    "civil_engineering":    "土木工程",
    "chemical_engineering": "化学工程",
    "biomedical_engineering": "生物医学工程",
    "aerospace_engineering": "航空航天工程",
    # 材料
    "materials_science":    "材料科学",
    "nanomaterials":        "纳米材料",
    "polymer_science":      "高分子科学",
    # 地球与环境
    "environmental_science": "环境科学",
    "geoscience":           "地球科学",
    "atmospheric_science":  "大气科学",
    "remote_sensing":       "遥感 / Remote Sensing",
    # 农学 / 能源
    "agriculture":          "农学",
    "food_science":         "食品科学",
    "energy_science":       "能源科学",
    # 通用
    "other":                "其他 / Other",
}

# ---------------------------------------------------------------------------
# 2. 学科 → 建议的数据文件格式
# ---------------------------------------------------------------------------
_CS_FORMATS = [
    {"label": "训练日志",       "exts": ".log .txt",            "desc": "训练过程输出 (loss/acc/epoch)"},
    {"label": "指标CSV/TSV",    "exts": ".csv .tsv",            "desc": "每行一条指标: step, metric, value"},
    {"label": "超参数配置",     "exts": ".yaml .yml .json",     "desc": "模型配置、超参数"},
    {"label": "TensorBoard数据","exts": ".csv",                 "desc": "从TB导出的标量CSV"},
    {"label": "预测结果",       "exts": ".csv .json",           "desc": "混淆矩阵、预测输出"},
    {"label": "结果截图",       "exts": ".png .jpg .svg",       "desc": "可视化结果、注意力图"},
    {"label": "论文表格",       "exts": ".csv .xlsx",           "desc": "对比实验结果"},
]

_PHYSICS_FORMATS = [
    {"label": "实验数据",       "exts": ".csv .tsv .xlsx",      "desc": "自变量/因变量/误差"},
    {"label": "光谱数据",       "exts": ".csv .txt",            "desc": "波长/频率 vs 强度"},
    {"label": "波形数据",       "exts": ".csv .txt",            "desc": "时域信号"},
    {"label": "仿真配置",       "exts": ".yaml .json",          "desc": "仿真软件参数"},
    {"label": "仿真结果",       "exts": ".csv .json .hdf5",     "desc": "FEM/Monte Carlo 输出"},
    {"label": "图像",           "exts": ".png .jpg .tif",       "desc": "显微镜/望远镜图像"},
]

_CHEMISTRY_FORMATS = [
    {"label": "光谱数据",       "exts": ".csv .txt .xlsx",      "desc": "IR/UV-Vis/NMR/质谱"},
    {"label": "反应动力学",     "exts": ".csv",                 "desc": "时间 vs 浓度/转化率"},
    {"label": "热分析",         "exts": ".csv .xlsx",           "desc": "DSC/TGA 曲线"},
    {"label": "色谱数据",       "exts": ".csv .txt",            "desc": "GC/HPLC 峰面积"},
    {"label": "晶体数据",       "exts": ".json .csv",           "desc": "XRD 衍射数据"},
    {"label": "量化计算日志",   "exts": ".log .txt .json",      "desc": "Gaussian/VASP 输出"},
    {"label": "分子结构图",     "exts": ".png .jpg .svg",       "desc": "分子结构/反应机理"},
]

_BIOLOGY_FORMATS = [
    {"label": "基因表达",       "exts": ".csv .tsv .xlsx",      "desc": "RNA-seq/微阵列表达矩阵"},
    {"label": "序列数据",       "exts": ".txt .csv",            "desc": "DNA/RNA/蛋白质序列"},
    {"label": "生存分析",       "exts": ".csv",                 "desc": "Kaplan-Meier 生存曲线"},
    {"label": "流式细胞",       "exts": ".csv",                 "desc": "散点/直方图数据"},
    {"label": "剂量反应",       "exts": ".csv .xlsx",           "desc": "浓度 vs 活性/抑制率"},
    {"label": "显微图像",       "exts": ".png .jpg .tif",       "desc": "荧光/共聚焦/电镜"},
    {"label": "统计结果",       "exts": ".csv .xlsx",           "desc": "t检验/ANOVA"},
]

_MEDICINE_FORMATS = [
    {"label": "临床数据",       "exts": ".csv .xlsx",           "desc": "患者指标/实验对照"},
    {"label": "医学影像",       "exts": ".png .jpg .tif",       "desc": "CT/MRI/X光"},
    {"label": "生存曲线",       "exts": ".csv",                 "desc": "Kaplan-Meier/Cox"},
    {"label": "ROC曲线数据",    "exts": ".csv",                 "desc": "敏感性 vs 特异性"},
    {"label": "药动学",         "exts": ".csv .xlsx",           "desc": "血药浓度-时间"},
    {"label": "统计分析",       "exts": ".csv .xlsx",           "desc": "多组对比检验"},
]

_ENGINEERING_FORMATS = [
    {"label": "测量数据",       "exts": ".csv .xlsx .tsv",      "desc": "传感器/测量读数"},
    {"label": "仿真结果",       "exts": ".csv .json .xlsx",     "desc": "FEA/CFD 输出"},
    {"label": "信号数据",       "exts": ".csv .txt",            "desc": "时域/频域波形"},
    {"label": "应力应变",       "exts": ".csv .xlsx",           "desc": "力学测试曲线"},
    {"label": "设计参数",       "exts": ".yaml .json",          "desc": "方案配置"},
    {"label": "结构图",         "exts": ".png .jpg .svg",       "desc": "设计图纸/示意图"},
    {"label": "性能对比",       "exts": ".csv .xlsx",           "desc": "方案 A vs B"},
]

_MATERIALS_FORMATS = [
    {"label": "XRD数据",        "exts": ".csv .txt .xlsx",      "desc": "2θ vs 强度"},
    {"label": "SEM/TEM图像",    "exts": ".png .jpg .tif",       "desc": "电镜图像"},
    {"label": "力学性能",       "exts": ".csv .xlsx",           "desc": "拉伸/压缩/硬度"},
    {"label": "热分析",         "exts": ".csv .xlsx",           "desc": "DSC/TGA"},
    {"label": "光谱",           "exts": ".csv .txt",            "desc": "UV-Vis/PL/Raman"},
    {"label": "电化学",         "exts": ".csv .xlsx",           "desc": "CV/EIS/充放电"},
]

_GEO_FORMATS = [
    {"label": "监测数据",       "exts": ".csv .xlsx .tsv",      "desc": "温度/湿度/浓度时间序列"},
    {"label": "遥感影像",       "exts": ".tif .png .jpg",       "desc": "卫星/无人机图像"},
    {"label": "GIS数据",        "exts": ".csv .json",           "desc": "地理坐标/空间分析"},
    {"label": "气象数据",       "exts": ".csv .nc",             "desc": "NetCDF 气象/海洋"},
    {"label": "样品分析",       "exts": ".csv .xlsx",           "desc": "土壤/水质成分"},
]

_GENERIC_FORMATS = [
    {"label": "实验数据",       "exts": ".csv .xlsx .tsv",      "desc": "通用表格数据"},
    {"label": "日志/记录",      "exts": ".log .txt",            "desc": "实验运行日志"},
    {"label": "配置文件",       "exts": ".yaml .yml .json",     "desc": "参数配置"},
    {"label": "图像",           "exts": ".png .jpg .svg .tif",  "desc": "结果图像"},
    {"label": "文档",           "exts": ".pdf .md",             "desc": "报告/说明"},
    {"label": "表格",           "exts": ".xlsx .csv",           "desc": "汇总表格"},
]

DISCIPLINE_FORMATS: Dict[str, List[dict]] = {
    "deep_learning": _CS_FORMATS, "machine_learning": _CS_FORMATS,
    "computer_vision": _CS_FORMATS, "nlp": _CS_FORMATS,
    "reinforcement_learning": _CS_FORMATS, "data_mining": _CS_FORMATS,
    "computer_science": _CS_FORMATS,

    "physics_general": _PHYSICS_FORMATS, "optics": _PHYSICS_FORMATS,
    "quantum_physics": _PHYSICS_FORMATS, "condensed_matter": _PHYSICS_FORMATS,
    "astrophysics": _PHYSICS_FORMATS,

    "chemistry_general": _CHEMISTRY_FORMATS, "organic_chemistry": _CHEMISTRY_FORMATS,
    "analytical_chemistry": _CHEMISTRY_FORMATS, "physical_chemistry": _CHEMISTRY_FORMATS,
    "biochemistry": _CHEMISTRY_FORMATS,

    "biology_general": _BIOLOGY_FORMATS, "molecular_biology": _BIOLOGY_FORMATS,
    "genomics": _BIOLOGY_FORMATS, "ecology": _BIOLOGY_FORMATS,
    "neuroscience": _BIOLOGY_FORMATS,

    "medicine": _MEDICINE_FORMATS, "clinical_medicine": _MEDICINE_FORMATS,
    "medical_imaging": _MEDICINE_FORMATS, "pharmacology": _MEDICINE_FORMATS,
    "public_health": _MEDICINE_FORMATS,

    "electrical_engineering": _ENGINEERING_FORMATS,
    "mechanical_engineering": _ENGINEERING_FORMATS,
    "civil_engineering": _ENGINEERING_FORMATS,
    "chemical_engineering": _ENGINEERING_FORMATS,
    "biomedical_engineering": _ENGINEERING_FORMATS,
    "aerospace_engineering": _ENGINEERING_FORMATS,

    "materials_science": _MATERIALS_FORMATS, "nanomaterials": _MATERIALS_FORMATS,
    "polymer_science": _MATERIALS_FORMATS,

    "environmental_science": _GEO_FORMATS, "geoscience": _GEO_FORMATS,
    "atmospheric_science": _GEO_FORMATS, "remote_sensing": _GEO_FORMATS,

    "mathematics": _GENERIC_FORMATS, "statistics": _GENERIC_FORMATS,
    "agriculture": _GENERIC_FORMATS, "food_science": _GENERIC_FORMATS,
    "energy_science": _ENGINEERING_FORMATS, "other": _GENERIC_FORMATS,
}


def get_formats_for_area(area: str) -> List[dict]:
    """Return suggested data formats for a research area."""
    return DISCIPLINE_FORMATS.get(area, _GENERIC_FORMATS)
