# Changelog / 更新日志

本项目遵循语义化版本（SemVer）与 Keep a Changelog 规范。
All notable changes follow Semantic Versioning and Keep a Changelog.

## [v0.1.0] - 2026-08-27 正式版 / Stable Release

### Added / 新增

- 数据分析模块（pandas + matplotlib）：营收、毛利率、现金流统计分析与可视化 / Data analysis module (pandas + matplotlib): revenue, gross margin, and cash flow statistics with visualisation
- 三级 PDF 解析引擎：pdfplumber → PyMuPDF → RapidOCR OCR 回退，解决复杂排版与图片型表格解析失败 / Three-tier PDF parsing engine with RapidOCR fallback for complex layouts and image-based tables
- 机器学习财务健康度分类：RandomForest，542 家企业、7 维现金流特征 / ML financial health classification (RandomForest, 542 companies, 7 cash-flow features)
- 深度学习财务健康度分类：PyTorch MLP（7→64→32→1，早停 + Dropout）/ DL financial health classification (PyTorch MLP with early stopping + Dropout)
- 模型可解释性分析：SHAP 特征重要性 + 方向性财务解读（外部融资依赖为最强负向信号）/ Model interpretability with SHAP: feature importance and directional financial insights
- 严谨化评估：5 折 Stratified 交叉验证 + ROC-AUC / Precision-Recall 指标（AUC ≈ 0.62）/ Rigorous evaluation with 5-fold Stratified Cross-Validation and ROC-AUC / PR metrics (AUC ≈ 0.62)

### Changed / 变更

- README 全面中英双语化，新增数据分析 / 机器学习 / 深度学习 / 可解释性章节 / README fully bilingual with analysis, ML, DL, and interpretability sections
- 依赖更新：新增 rapidocr_onnxruntime、torch、shap / Dependencies updated: rapidocr_onnxruntime, torch, shap

## [v0.1.0-alpha.1] - 2026-08-07

### Added / 新增

- SQLite 持久化与日期范围查询（`crawl_state.db`），解决公告页码漂移问题 / SQLite persistence with date-range querying, eliminating announcement page drift
- 断点续爬：启动时自动恢复中断下载、WAL 模式 + busy_timeout / Resume support with automatic recovery of interrupted downloads
- 端到端冒烟测试 / End-to-end smoke test

### Fixed / 修复

- `_has_complete_csvs` 增加年份参数，修复多年度公告误跳过 / Added year parameter to prevent false skipping of multi-year announcements

## 2026-08-05 项目初始化 / Project Initiation

- 新三板与巨潮资讯网年报爬虫骨架：公告搜索、PDF 下载、CSV 导出 / NEEQ & CNINFO annual report crawler skeleton: announcement search, PDF download, CSV export
